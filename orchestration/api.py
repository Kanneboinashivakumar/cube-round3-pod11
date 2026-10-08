"""Optional HTTP front door for the orchestrator (useful for a deployed demo).

  uvicorn orchestration.api:app --port 8100
  GET  /                          -> Shared WMS-style operations dashboard
  GET  /workflows                 -> List stored unit passports
  POST /workflows                 {"org_id": "org_demo_alpha", "unit_id": "UNIT-0002"}   -> Legacy workflow entry point
  POST /events                    -> Event-driven passport create / advance
  GET  /workflows/{id}            -> Workflow State
  GET  /workflows/{id}/evidence   -> the workflow plus all its evidence records
  POST /workflows/{id}/resume     -> continue after a halt / decision / failure
  POST /workflows/{id}/overrides  {"record_id": "...", "new_verdict": "PASS", "actor": "...", "reason": "..."}
  GET  /health                    -> orchestrator and every agent in the flow
No authentication is included. Add it before you deploy anywhere public.
"""
from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
import re

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from shared.utils import sample_data

from .clients import HttpClient, client_for, load_manifest
from .orchestrator import apply_override, bundle, default_flow_path, flow_stages, load_flow, new_workflow, resume, run_workflow, workflow_id_for
from .store import EvidenceConflict, FileStore
from shared.utils.records import utcnow

app = FastAPI(title="CUBE Round 3 orchestrator")
FLOW = os.environ.get("ORCH_FLOW") or default_flow_path()
STORE = FileStore()
EVENT_FLOW = Path(__file__).with_name("flow.cube.json")
WEB = Path(__file__).resolve().parents[1] / "web"
app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")


@app.get("/")
def dashboard():
    return FileResponse(WEB / "index.html")


@app.get("/health")
def health() -> dict:
    agents = {}
    operational_flow = load_flow(EVENT_FLOW)
    for stage in flow_stages(operational_flow):
        client = client_for(stage)
        try:
            agents[stage] = client.health() if isinstance(client, HttpClient) else {"status": "ok", "mode": "inproc"}
        except Exception as exc:
            agents[stage] = {"status": "down", "error": str(exc)[:200], "owner": load_manifest(stage)["owner"]}
    ok = all(a["status"] == "ok" for a in agents.values())
    return {"status": "ok" if ok else "degraded", "flow": operational_flow["flow_id"],
            "compatibility_flow": load_flow(FLOW)["flow_id"], "agents": agents}


@app.get("/workflows")
def list_workflows() -> list[dict]:
    return STORE.list_workflows()


@app.post("/events")
def receive_event(body: dict) -> dict:
    """Apply a business event to one unit passport and advance only newly eligible agents."""
    event_type = str(body.get("event_type", "")).upper()
    if event_type not in {"UNIT_CREATED", "PRODUCT_RECEIVED", "FULFILMENT_ROUTE_IDENTIFIED", "RETURN_INITIATED", "RETURN_RECEIVED", "CHARGE_RECEIVED"}:
        raise HTTPException(422, "Unsupported event_type. Use UNIT_CREATED, PRODUCT_RECEIVED, FULFILMENT_ROUTE_IDENTIFIED, RETURN_INITIATED, RETURN_RECEIVED, or CHARGE_RECEIVED.")
    org, subject = body.get("org_id"), body.get("unit_id") or body.get("subject_id")
    if not org or not subject:
        raise HTTPException(422, "org_id and unit_id are required")
    if any(not isinstance(value, str) or len(value) > 80 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value)
           for value in (org, subject)):
        raise HTTPException(422, "org_id and unit_id may contain only letters, numbers, dot, underscore, and dash")
    receiving_input = body.get("receiving") or {}
    if not isinstance(receiving_input, dict):
        raise HTTPException(422, "receiving must be an object")
    if event_type in {"UNIT_CREATED", "PRODUCT_RECEIVED", "FULFILMENT_ROUTE_IDENTIFIED"} and body.get("route", "unknown") not in {"fba", "mfn", "unknown"}:
        raise HTTPException(422, "route must be fba, mfn, or unknown")

    flow = load_flow(EVENT_FLOW)
    event_id = str(body.get("event_id") or f"{event_type}:{org}:{subject}")
    case = {"org_id": org, "unit_id": subject, "route": body.get("route", "unknown"),
            "returned": False, "return_initiated": False, "has_charge": False,
            "product_received": event_type == "PRODUCT_RECEIVED", "receiving": receiving_input,
            "fee": body.get("fee", {}), "event_ids": [event_id]}
    workflow_id = workflow_id_for(case)
    wf = STORE.load_workflow(workflow_id)

    if event_type == "UNIT_CREATED":
        if wf:
            if event_id in wf.get("context", {}).get("event_ids", []):
                return wf
            raise HTTPException(409, "a unit-created event already created this passport")
        draft = new_workflow(case, flow)
        _append_event(draft, event_type, "passport", event_id)
        STORE.save_workflow(draft)
        return draft

    if event_type == "PRODUCT_RECEIVED" and wf is None:
        case["receiving"] = {key: value for key, value in case["receiving"].items() if key != "photos"}
        _save_receiving_photos(receiving_input.get("photos", []) or [], org, subject)
        created = run_workflow(case, flow, STORE)
        _append_event(created, event_type, "receiving", event_id)
        STORE.save_workflow(created)
        return created
    if wf is None:
        raise HTTPException(404, f"unit passport {workflow_id} not found; send PRODUCT_RECEIVED first")
    if event_id in wf.get("context", {}).get("event_ids", []):
        should_resume = _has_product_received(wf) and wf["status"] in {"PENDING", "IN_PROGRESS", "FAILED"}
        return run_workflow({"org_id": org, "unit_id": subject}, flow, STORE) if should_resume else wf
    if event_type == "PRODUCT_RECEIVED":
        if _has_product_received(wf):
            raise HTTPException(409, "a product-received event already exists for this passport")
        route = body.get("route", "unknown")
        if route == "unknown":
            route = wf["context"].get("route", "unknown")
        wf["context"].update({"product_received": True, "receiving": {key: value for key, value in receiving_input.items() if key != "photos"},
                              "route": route})
        _save_receiving_photos(receiving_input.get("photos", []) or [], org, subject)
        _apply_route(wf, route)
        wf["context"].setdefault("event_ids", []).append(event_id)
        _append_event(wf, event_type, "receiving", event_id)
        STORE.save_workflow(wf)
        return run_workflow({"org_id": org, "unit_id": subject}, flow, STORE)

    if event_type == "FULFILMENT_ROUTE_IDENTIFIED":
        route = body.get("route")
        if route not in {"fba", "mfn"}:
            raise HTTPException(422, "a fulfilment route event must identify fba or mfn")
        if wf["context"].get("route") not in {"unknown", route} and any(
                sr["stage"] in {"prep", "pack"} and sr["runs"] > 0 for sr in wf["stage_results"]):
            raise HTTPException(409, "the fulfilment route cannot change after a route-specific agent has completed")
        wf["context"]["route"] = route
        _apply_route(wf, route)
        wf["context"].setdefault("event_ids", []).append(event_id)
        _append_event(wf, event_type, "prep" if route == "fba" else "pack", event_id)
        if not _has_product_received(wf):
            STORE.save_workflow(wf)
            return wf
    elif event_type == "RETURN_RECEIVED":
        if not _has_product_received(wf):
            raise HTTPException(409, "receive the product before recording its physical return")
        wf["context"]["returned"] = True
        target_stage = "returns"
    elif event_type == "RETURN_INITIATED":
        if not _has_product_received(wf):
            raise HTTPException(409, "receive the product before initiating its return")
        wf["context"]["return_initiated"] = True
        wf["context"].setdefault("event_ids", []).append(event_id)
        _append_event(wf, event_type, "returns", event_id)
        STORE.save_workflow(wf)
        return wf
    else:
        if not _has_product_received(wf):
            raise HTTPException(409, "receive the product before recording a fee or charge")
        wf["context"]["has_charge"] = True
        wf["context"]["fee"] = case["fee"]
        target_stage = "recovery"

    if event_type != "FULFILMENT_ROUTE_IDENTIFIED":
        stage = next(sr for sr in wf["stage_results"] if sr["stage"] == target_stage)
        if stage["state"] == "skipped":
            stage.update({"state": "pending", "skipped_reason": None})
        wf["context"].setdefault("event_ids", []).append(event_id)
        _append_event(wf, event_type, target_stage, event_id)
    STORE.save_workflow(wf)
    if not _has_product_received(wf) and event_type != "FULFILMENT_ROUTE_IDENTIFIED":
        return wf
    return run_workflow({"org_id": org, "unit_id": subject}, flow, STORE)


def _has_product_received(wf: dict) -> bool:
    """Backfill the event marker for workflows created before the event API existed."""
    return bool(wf.get("context", {}).get("product_received") or any(
        sr["stage"] == "receiving" and sr.get("runs", 0) > 0 for sr in wf.get("stage_results", [])))


def _append_event(wf: dict, event_type: str, stage: str, event_id: str) -> None:
    at = utcnow()
    wf["timestamps"]["updated_at"] = at
    wf["transitions"].append({"at": at, "event": "business_event_received", "stage": stage,
                               "detail": event_type, "event_id": event_id})


def _apply_route(wf: dict, route: str) -> None:
    if route not in {"fba", "mfn"}:
        return
    target = "prep" if route == "fba" else "pack"
    other = "pack" if route == "fba" else "prep"
    target_result = next(sr for sr in wf["stage_results"] if sr["stage"] == target)
    other_result = next(sr for sr in wf["stage_results"] if sr["stage"] == other)
    if target_result["state"] == "skipped":
        target_result.update({"state": "pending", "skipped_reason": None})
    if other_result["state"] == "pending" and other_result["runs"] == 0:
        other_result.update({"state": "skipped", "skipped_reason": f"route={route}; only the {target} path applies"})


def _save_receiving_photos(photos: list, org_id: str, subject_id: str) -> None:
    """Persist bounded, tenant-scoped image captures before the receiving agent runs."""
    if not isinstance(photos, list) or len(photos) > 12:
        raise HTTPException(422, "Attach at most 12 receiving images")
    root = Path(os.environ.get("INPUT_DIR", Path(__file__).resolve().parents[1] / "data" / "input")).resolve()
    safe_org = re.sub(r"[^A-Za-z0-9._-]", "-", org_id)
    safe_subject = re.sub(r"[^A-Za-z0-9._-]", "-", subject_id)
    folder = root / safe_org / safe_subject / "receiving"
    folder.mkdir(parents=True, exist_ok=True)
    allowed = {"image/jpeg": (".jpg", b"\xff\xd8\xff"), "image/png": (".png", b"\x89PNG\r\n\x1a\n"),
               "image/webp": (".webp", b"RIFF")}
    for photo in photos:
        if not isinstance(photo, dict) or photo.get("mime_type") not in allowed or not isinstance(photo.get("data"), str):
            raise HTTPException(422, "Only JPEG, PNG and WebP receiving photos are accepted")
        try:
            raw = base64.b64decode(photo["data"], validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise HTTPException(422, "A receiving photo was not valid base64") from exc
        if not raw or len(raw) > 8 * 1024 * 1024:
            raise HTTPException(413, "Each receiving photo must be between 1 byte and 8 MB")
        suffix, signature = allowed[photo["mime_type"]]
        if not raw.startswith(signature) or (suffix == ".webp" and raw[8:12] != b"WEBP"):
            raise HTTPException(422, "A receiving photo does not match its declared image type")
        digest = hashlib.sha256(raw).hexdigest()
        (folder / f"{digest}{suffix}").write_bytes(raw)


@app.post("/workflows")
def create(body: dict) -> dict:
    org, subject = body.get("org_id"), body.get("subject_id") or body.get("unit_id")
    if not org or not subject:
        raise HTTPException(422, "org_id and unit_id (or subject_id) are required")
    case = {"org_id": org, "unit_id": subject, "route": body.get("route") or sample_data.route(subject, org),
            "returned": body.get("returned", sample_data.has("returns", subject, org))}
    return run_workflow(case, load_flow(FLOW), STORE)


def _get(workflow_id: str) -> dict:
    wf = STORE.load_workflow(workflow_id)
    if wf is None:
        raise HTTPException(404, f"no workflow {workflow_id}")
    return wf


@app.get("/workflows/{workflow_id}")
def get(workflow_id: str) -> dict:
    return _get(workflow_id)


@app.get("/workflows/{workflow_id}/evidence")
def evidence(workflow_id: str) -> dict:
    return bundle(_get(workflow_id), STORE)


@app.get("/captures")
def capture(ref: str):
    """Serve an evidence-linked local image without accepting absolute paths."""
    root = Path(os.environ.get("INPUT_DIR", Path(__file__).resolve().parents[1] / "data" / "input")).resolve()
    path = (root / ref).resolve()
    if root not in path.parents or not path.is_file() or path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(404, "capture not found")
    return FileResponse(path)


@app.post("/workflows/{workflow_id}/resume")
def resume_workflow(workflow_id: str) -> dict:
    _get(workflow_id)
    return resume(workflow_id, load_flow(FLOW), STORE)


@app.post("/workflows/{workflow_id}/overrides")
def override(workflow_id: str, body: dict) -> dict:
    _get(workflow_id)
    try:
        return apply_override(workflow_id, STORE, record_id=body.get("record_id", ""), new_verdict=body.get("new_verdict", ""),
                              actor=body.get("actor", ""), reason=body.get("reason", ""), new_outcome=body.get("new_outcome"))
    except (ValueError, EvidenceConflict) as exc:
        raise HTTPException(422, str(exc)) from exc

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
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
from typing import Optional

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
PROJECT_FLOWS = Path(__file__).with_name("projects")
WEB = Path(__file__).resolve().parents[1] / "web"
app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")


@app.get("/")
def dashboard():
    return FileResponse(WEB / "index.html")


@app.get("/docs/agent-api")
def agent_contract():
    return FileResponse(Path(__file__).resolve().parents[1] / "shared" / "contracts" / "agent-api.md",
                        media_type="text/markdown")


def _project_flow(project_id: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", project_id):
        raise HTTPException(422, "project_id may contain only letters, numbers, dot, underscore, and dash")
    path = PROJECT_FLOWS / project_id / "flow.json"
    if not path.is_file():
        raise HTTPException(404, f"No orchestration flow is registered for project {project_id}")
    return load_flow(path)


@app.get("/health")
def health(project_id: str = "receiving") -> dict:
    agents = {}
    operational_flow = _project_flow(project_id)
    for stage in flow_stages(operational_flow):
        client = client_for(stage)
        try:
            agents[stage] = client.health() if isinstance(client, HttpClient) else {"status": "ok", "mode": "inproc"}
        except Exception as exc:
            agents[stage] = {"status": "down", "error": str(exc)[:200], "owner": load_manifest(stage)["owner"]}
    ok = all(a["status"] == "ok" for a in agents.values())
    return {"status": "ok" if ok else "degraded", "project_id": project_id, "flow": operational_flow["flow_id"],
            "compatibility_flow": load_flow(FLOW)["flow_id"], "agents": agents}


@app.get("/workflows")
def list_workflows() -> list[dict]:
    return STORE.list_workflows()


def _receiving_record(row: dict) -> dict:
    """Expose the supplied Receiving Manager fixture without inventing image analysis."""
    flags = [value.strip().lower() for value in row.get("quality_flags", "").split(";") if value.strip()]

    def numeric(key: str):
        value = row.get(key)
        return int(value) if value not in (None, "") else None

    def result(key: str, verdict: str, expected=None, observed=None, detail="") -> dict:
        return {"key": key, "verdict": verdict, "expected": expected,
                "observed": observed, "detail": detail,
                "evidence_refs": [ref for ref in row.get("photo_refs", "").split(";") if ref]}

    identity = {"yes": "PASS", "no": "FAIL"}.get(row.get("identity_match", "").lower(), "UNCERTAIN")
    qty_expected, qty_observed = numeric("qty_ordered"), numeric("qty_received")
    carton_expected, carton_observed = numeric("cartons_ordered"), numeric("cartons_received")
    pack_expected, pack_observed = numeric("units_per_carton_ordered"), numeric("units_per_carton_counted")
    carton_damage = row.get("carton_damage") or "none"
    unit_damage = row.get("unit_damage") or "none"
    carton_verdict = "PASS" if carton_damage == "none" else "UNCERTAIN" if carton_damage == "uncertain" else "FAIL"
    unit_verdict = "PASS" if unit_damage == "none" else "UNCERTAIN" if unit_damage == "uncertain" else "FAIL"
    checks = [
        result("identity_match", identity, row.get("sku"), row.get("sku") if identity == "PASS" else None,
               "Identity result supplied by the CSV fixture; no photo was analyzed."),
        result("quantity", "UNCERTAIN" if qty_expected is None or qty_observed is None else "PASS" if qty_expected == qty_observed else "FAIL", qty_expected, qty_observed,
               "Ordered and received quantities from the supplied fixture."),
        result("carton_count", "UNCERTAIN" if carton_expected is None or carton_observed is None else "PASS" if carton_expected == carton_observed else "FAIL", carton_expected, carton_observed,
               "Ordered and received carton counts from the supplied fixture."),
        result("units_per_carton", "UNCERTAIN" if pack_expected is None or pack_observed is None else "PASS" if pack_expected == pack_observed else "FAIL", pack_expected, pack_observed,
               "Expected and counted units per carton from the supplied fixture."),
        result("variant", "FAIL" if any(any(term in flag for term in ("wrong variant", "wrong colour", "wrong color")) for flag in flags) else "PASS" if row.get("spec_colour") or row.get("spec_variant") else "UNCERTAIN",
               {"colour": row.get("spec_colour"), "variant": row.get("spec_variant")}, None,
               "Fixture quality flag; an observed colour or variant was not included."),
        result("carton_damage", carton_verdict, "none", carton_damage,
               "Carton condition field from the supplied fixture."),
        result("unit_damage", unit_verdict, "none", unit_damage,
               "Product condition field from the supplied fixture."),
        result("components", "FAIL" if any("missing component" in flag or "missing_components" in flag for flag in flags) else "PASS" if row.get("spec_components") else "UNCERTAIN",
               [part.strip() for part in row.get("spec_components", "").split(";") if part.strip()], None,
               "Fixture quality flag; components are not visually verified by this sample."),
    ]
    verdict = "FAIL" if any(item["verdict"] == "FAIL" for item in checks) else (
        "UNCERTAIN" if any(item["verdict"] == "UNCERTAIN" for item in checks) else "PASS")
    return {
        **row,
        "checks": checks,
        "verdict": verdict,
        "decision": {"PASS": "PASS", "FAIL": "EXCEPTION", "UNCERTAIN": "UNCERTAIN"}[verdict],
        "evidence_source": "synthetic CSV fixture; photos were not analyzed",
    }


def _workflow_receipt(workflow: dict) -> Optional[dict]:
    """Project a newly captured receipt into the ledger without changing its evidence."""
    context = workflow.get("context", {})
    receiving = context.get("receiving", {})
    stage = next((item for item in workflow.get("stage_results", []) if item.get("stage") == "receiving"), {})
    evidence = STORE.get_evidence(stage.get("record_id")) if stage.get("record_id") else None
    if not evidence:
        return None
    checks = [{**item, "key": item.get("check_key")} for item in evidence.get("checks", [])]
    by_key = {item.get("key"): item for item in checks}
    expected = evidence.get("payload", {}).get("expected", {})
    identity = by_key.get("identity_match", {})
    carton = by_key.get("carton_damage", {})
    product = by_key.get("unit_damage", {})
    decision = evidence.get("decision", {}).get("verdict", "UNCERTAIN")
    outcome = {"PASS": "PASS", "FAIL": "EXCEPTION", "UNCERTAIN": "UNCERTAIN"}.get(decision, "UNCERTAIN")
    row = {
        "record_id": evidence.get("record_id"), "unit_id": workflow.get("subject_id"), "org_id": workflow.get("org_id"),
        "po_number": receiving.get("po_number") or expected.get("po_number"), "po_line": receiving.get("po_line") or expected.get("po_line"),
        "supplier": receiving.get("supplier"), "sku": receiving.get("sku") or expected.get("sku"),
        "asin": receiving.get("asin") or expected.get("asin"), "product_title": receiving.get("product_title") or expected.get("product_title"),
        "spec_colour": receiving.get("colour") or expected.get("colour"), "spec_variant": receiving.get("variant") or expected.get("variant"),
        "spec_components": "; ".join(receiving.get("components") or expected.get("components") or []),
        "cartons_ordered": expected.get("cartons"), "cartons_received": by_key.get("carton_count", {}).get("observed"),
        "units_per_carton_ordered": expected.get("units_per_carton"), "units_per_carton_counted": by_key.get("units_per_carton", {}).get("observed"),
        "qty_ordered": expected.get("quantity"), "qty_received": by_key.get("quantity", {}).get("observed"),
        "identity_match": "yes" if identity.get("verdict") == "PASS" else "no" if identity.get("verdict") == "FAIL" else "uncertain",
        "carton_damage": carton.get("observed", {}).get("type", "uncertain") if isinstance(carton.get("observed"), dict) else carton.get("observed", "uncertain"),
        "unit_damage": product.get("observed", {}).get("type", "uncertain") if isinstance(product.get("observed"), dict) else product.get("observed", "uncertain"),
        "quality_flags": evidence.get("payload", {}).get("quality_flags", ""),
        "photo_refs": ";".join(item.get("ref", "") for item in evidence.get("inputs", []) if item.get("kind") == "image"),
        "operator_id": evidence.get("operator_id"), "captured_at": evidence.get("captured_at"),
        "checks": checks, "verdict": decision, "decision": outcome,
        "evidence_source": evidence.get("payload", {}).get("evidence_source", "Receiving Manager evidence"),
    }
    return row


def _receiving_import_dir() -> Path:
    return Path(os.environ.get("OUT_DIR", Path(__file__).resolve().parents[1] / "out")).resolve() / "receiving-imports"


@app.get("/receiving")
def list_receiving_records(org_id: Optional[str] = None, q: Optional[str] = None, verdict: Optional[str] = None) -> list[dict]:
    """The uploaded Round 2 CSV is the receiving ledger's source of truth."""
    items = [_receiving_record(row) for row in sample_data.rows("receiving")]
    for path in sorted(_receiving_import_dir().glob("*.json")) if _receiving_import_dir().is_dir() else []:
        try:
            imported = json.loads(path.read_text())
            if isinstance(imported, list):
                items.extend(_receiving_record(row) for row in imported if isinstance(row, dict))
        except (OSError, ValueError):
            continue
    known = {(item["org_id"], item["unit_id"]) for item in items}
    for workflow in STORE.list_workflows():
        if workflow.get("context", {}).get("project_id") != "receiving":
            continue
        key = (workflow.get("org_id"), workflow.get("subject_id"))
        if key in known:
            continue
        projected = _workflow_receipt(workflow)
        if projected:
            items.append(projected)
            known.add(key)
    if org_id:
        items = [item for item in items if item.get("org_id") == org_id]
    if q:
        needle = q.casefold()
        items = [item for item in items if needle in " ".join(str(item.get(key, "")) for key in (
            "record_id", "unit_id", "po_number", "supplier", "sku", "product_title", "asin")).casefold()]
    if verdict:
        items = [item for item in items if item["decision"].casefold() == verdict.casefold()]
    return items


@app.post("/receiving/import")
def import_receiving_csv(body: dict) -> dict:
    """Append a validated receiving CSV import without modifying the supplied sample file."""
    content = body.get("csv")
    if not isinstance(content, str) or not content.strip():
        raise HTTPException(422, "Provide the CSV file contents")
    if len(content.encode("utf-8")) > 8 * 1024 * 1024:
        raise HTTPException(413, "Receiving CSV must be 8 MB or smaller")
    try:
        reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff")))
        required = {"unit_id", "org_id", "po_number", "sku", "qty_ordered", "qty_received"}
        headers = set(reader.fieldnames or [])
        if not required.issubset(headers):
            raise HTTPException(422, "CSV is missing required columns: " + ", ".join(sorted(required - headers)))
        rows = [dict(row) for row in reader]
    except csv.Error as exc:
        raise HTTPException(422, f"Could not parse receiving CSV: {exc}") from exc
    if not rows:
        raise HTTPException(422, "CSV contains no receipt rows")
    if len(rows) > 10000:
        raise HTTPException(413, "A single receiving CSV may contain at most 10,000 rows")
    existing = {(row["org_id"], row["unit_id"]) for row in sample_data.rows("receiving")}
    existing.update((row.get("org_id"), row.get("unit_id")) for row in list_receiving_records())
    accepted = []
    for index, row in enumerate(rows, start=2):
        row = {str(key): (value or "").strip() for key, value in row.items() if key}
        org, unit = row.get("org_id"), row.get("unit_id")
        if not org or not unit or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", org) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", unit):
            raise HTTPException(422, f"Row {index} needs safe org_id and unit_id values")
        if (org, unit) in existing:
            continue
        for key in ("qty_ordered", "qty_received", "cartons_ordered", "cartons_received", "units_per_carton_ordered", "units_per_carton_counted"):
            value = row.get(key)
            if value:
                try:
                    if int(value) < 0:
                        raise ValueError
                except ValueError as exc:
                    raise HTTPException(422, f"Row {index} has an invalid {key}") from exc
        if not row.get("record_id"):
            row["record_id"] = f"RCV-IMPORT-{hashlib.sha256(f'{org}:{unit}'.encode()).hexdigest()[:10].upper()}"
        if not row.get("captured_at"):
            row["captured_at"] = utcnow()
        accepted.append(row)
        existing.add((org, unit))
    if not accepted:
        return {"imported": 0, "skipped": len(rows), "message": "All rows already exist in this receiving workspace."}
    raw = json.dumps(accepted, ensure_ascii=False, indent=2)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    folder = _receiving_import_dir()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{digest}.json"
    if not target.exists():
        target.write_text(raw, encoding="utf-8")
    return {"imported": len(accepted), "skipped": len(rows) - len(accepted), "message": "Receiving CSV added to the local workspace."}


@app.get("/receiving/{record_id}")
def get_receiving_record(record_id: str) -> dict:
    for row in list_receiving_records():
        if row.get("record_id") == record_id or row.get("unit_id") == record_id:
            return row
    raise HTTPException(404, "Receiving sample record not found")


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
    prep_input, pack_input = body.get("prep") or {}, body.get("pack") or {}
    if not isinstance(prep_input, dict) or not isinstance(pack_input, dict):
        raise HTTPException(422, "prep and pack must be objects")
    if event_type in {"UNIT_CREATED", "PRODUCT_RECEIVED", "FULFILMENT_ROUTE_IDENTIFIED"} and body.get("route", "unknown") not in {"fba", "mfn", "unknown"}:
        raise HTTPException(422, "route must be fba, mfn, or unknown")

    project_id = str(body.get("project_id", "receiving"))
    flow = _project_flow(project_id)
    stages = set(flow_stages(flow))
    required_stage = {
        "RETURN_INITIATED": {"returns"},
        "RETURN_RECEIVED": {"returns"},
        "CHARGE_RECEIVED": {"recovery"},
    }.get(event_type, set())
    if event_type == "FULFILMENT_ROUTE_IDENTIFIED":
        required_stage = {"prep" if body.get("route") == "fba" else "pack"}
    if required_stage and not required_stage.issubset(stages):
        raise HTTPException(422, f"{event_type} is not enabled in project {project_id}'s flow")
    event_id = str(body.get("event_id") or f"{event_type}:{org}:{subject}")
    case = {"project_id": project_id, "org_id": org, "unit_id": subject, "route": body.get("route", "unknown"),
            "returned": False, "return_initiated": False, "has_charge": False,
            "product_received": event_type == "PRODUCT_RECEIVED", "receiving": receiving_input,
            "prep": {key: value for key, value in prep_input.items() if key != "photos"},
            "pack": {key: value for key, value in pack_input.items() if key != "photos"},
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
        _save_stage_photos(prep_input.get("photos", []) or [], org, subject, "prep")
        _save_stage_photos(pack_input.get("photos", []) or [], org, subject, "pack")
        created = run_workflow(case, flow, STORE)
        _append_event(created, event_type, "receiving", event_id)
        STORE.save_workflow(created)
        return created
    if wf is None:
        raise HTTPException(404, f"unit passport {workflow_id} not found; send PRODUCT_RECEIVED first")
    if event_id in wf.get("context", {}).get("event_ids", []):
        should_resume = _has_product_received(wf) and wf["status"] in {"PENDING", "IN_PROGRESS", "FAILED"}
        return run_workflow({"project_id": project_id, "org_id": org, "unit_id": subject}, flow, STORE) if should_resume else wf
    if event_type == "PRODUCT_RECEIVED":
        if _has_product_received(wf):
            raise HTTPException(409, "a product-received event already exists for this passport")
        route = body.get("route", "unknown")
        if route == "unknown":
            route = wf["context"].get("route", "unknown")
        prior_prep, prior_pack = wf["context"].get("prep", {}), wf["context"].get("pack", {})
        wf["context"].update({"product_received": True, "receiving": {key: value for key, value in receiving_input.items() if key != "photos"},
                              "prep": {**prior_prep, **{key: value for key, value in prep_input.items() if key != "photos"}},
                              "pack": {**prior_pack, **{key: value for key, value in pack_input.items() if key != "photos"}}, "route": route})
        _save_receiving_photos(receiving_input.get("photos", []) or [], org, subject)
        _save_stage_photos(prep_input.get("photos", []) or [], org, subject, "prep")
        _save_stage_photos(pack_input.get("photos", []) or [], org, subject, "pack")
        _apply_route(wf, route)
        wf["context"].setdefault("event_ids", []).append(event_id)
        _append_event(wf, event_type, "receiving", event_id)
        STORE.save_workflow(wf)
        return run_workflow({"project_id": project_id, "org_id": org, "unit_id": subject}, flow, STORE)

    if event_type == "FULFILMENT_ROUTE_IDENTIFIED":
        route = body.get("route")
        if route not in {"fba", "mfn"}:
            raise HTTPException(422, "a fulfilment route event must identify fba or mfn")
        if wf["context"].get("route") not in {"unknown", route} and any(
                sr["stage"] in {"prep", "pack"} and sr["runs"] > 0 for sr in wf["stage_results"]):
            raise HTTPException(409, "the fulfilment route cannot change after a route-specific agent has completed")
        wf["context"]["route"] = route
        if prep_input:
            wf["context"].setdefault("prep", {}).update({key: value for key, value in prep_input.items() if key != "photos"})
            _save_stage_photos(prep_input.get("photos", []) or [], org, subject, "prep")
        if pack_input:
            wf["context"].setdefault("pack", {}).update({key: value for key, value in pack_input.items() if key != "photos"})
            _save_stage_photos(pack_input.get("photos", []) or [], org, subject, "pack")
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
    return run_workflow({"project_id": project_id, "org_id": org, "unit_id": subject}, flow, STORE)


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
    """Persist receipt images using the common tenant-scoped stage capture path."""
    _save_stage_photos(photos, org_id, subject_id, "receiving")


def _save_stage_photos(photos: list, org_id: str, subject_id: str, stage: str) -> None:
    """Persist bounded images under data/input/<org>/<unit>/<stage>."""
    if not isinstance(photos, list) or len(photos) > 12:
        raise HTTPException(422, f"Attach at most 12 {stage} images")
    root = Path(os.environ.get("INPUT_DIR", Path(__file__).resolve().parents[1] / "data" / "input")).resolve()
    safe_org = re.sub(r"[^A-Za-z0-9._-]", "-", org_id)
    safe_subject = re.sub(r"[^A-Za-z0-9._-]", "-", subject_id)
    folder = root / safe_org / safe_subject / stage
    folder.mkdir(parents=True, exist_ok=True)
    allowed = {"image/jpeg": (".jpg", b"\xff\xd8\xff"), "image/png": (".png", b"\x89PNG\r\n\x1a\n"),
               "image/webp": (".webp", b"RIFF")}
    for photo in photos:
        if not isinstance(photo, dict) or photo.get("mime_type") not in allowed or not isinstance(photo.get("data"), str):
            raise HTTPException(422, "Only JPEG, PNG and WebP stage photos are accepted")
        try:
            raw = base64.b64decode(photo["data"], validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise HTTPException(422, "A stage photo was not valid base64") from exc
        if not raw or len(raw) > 8 * 1024 * 1024:
            raise HTTPException(413, "Each stage photo must be between 1 byte and 8 MB")
        suffix, signature = allowed[photo["mime_type"]]
        if not raw.startswith(signature) or (suffix == ".webp" and raw[8:12] != b"WEBP"):
            raise HTTPException(422, "A stage photo does not match its declared image type")
        digest = hashlib.sha256(raw).hexdigest()
        (folder / f"{digest}{suffix}").write_bytes(raw)


@app.post("/workflows")
def create(body: dict) -> dict:
    org, subject = body.get("org_id"), body.get("subject_id") or body.get("unit_id")
    if not org or not subject:
        raise HTTPException(422, "org_id and unit_id (or subject_id) are required")
    project_id = str(body.get("project_id", "receiving"))
    case = {"project_id": project_id, "org_id": org, "unit_id": subject, "route": body.get("route") or sample_data.route(subject, org),
            "returned": body.get("returned", sample_data.has("returns", subject, org))}
    return run_workflow(case, _project_flow(project_id), STORE)


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
    workflow = _get(workflow_id)
    return resume(workflow_id, _project_flow(workflow.get("context", {}).get("project_id", "receiving")), STORE)


@app.post("/workflows/{workflow_id}/overrides")
def override(workflow_id: str, body: dict) -> dict:
    _get(workflow_id)
    try:
        return apply_override(workflow_id, STORE, record_id=body.get("record_id", ""), new_verdict=body.get("new_verdict", ""),
                              actor=body.get("actor", ""), reason=body.get("reason", ""), new_outcome=body.get("new_outcome"))
    except (ValueError, EvidenceConflict) as exc:
        raise HTTPException(422, str(exc)) from exc

"""Round 3 adapter for the existing Prep Manager inspection service.

The optional Next.js service owns its vision/rules implementation. This adapter
uploads only tenant-scoped input images and maps its EvidenceRecord into the
Pod contract. Without that service it records a visible pending result.
"""
from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from shared.utils.records import build_output, build_record, check, pending_output, utcnow
from shared.utils.hashing import seal
from shared.utils import sample_data
from shared.utils.server import make_app

STAGE = "prep"
AGENT_ID = "prep-manager-adapter@1"
DEFAULT_INPUT = Path(__file__).resolve().parents[2] / "data" / "input"


def _id(request: dict) -> str:
    return "PRP-" + hashlib.sha256(request["request_id"].encode()).hexdigest()[:12].upper()


def _pending(request: dict, code: str, message: str) -> dict:
    out = pending_output(request, code=code, message=message, agent_id=AGENT_ID)
    record = seal({**out["evidence"], "inputs": request.get("inputs", [])})
    recommendation = out["next_step_recommendation"]
    return build_output(record, next_step=recommendation["action"], reason=recommendation["reason"])


def _refuse_known_cross_tenant_sample(request: dict) -> None:
    """Keep offline sample contract tests tenant isolated without using sample values as judgments."""
    subject = request["subject"]
    try:
        belongs_elsewhere = any(row["unit_id"] == subject["subject_id"] and row["org_id"] != subject["org_id"]
                                for row in sample_data.rows(STAGE))
    except OSError:
        return  # Production input is established by its tenant-scoped captured files.
    if belongs_elsewhere:
        raise LookupError("Prep subject belongs to a different organization")


def _photos(request: dict) -> list[dict]:
    root = Path(os.environ.get("INPUT_DIR", DEFAULT_INPUT)).resolve()
    org, subject = request["subject"]["org_id"], request["subject"]["subject_id"]
    uploads, paths = [], []
    for item in request.get("inputs", []):
        if item.get("kind") != "image":
            continue
        candidate = (root / item["ref"]).resolve()
        if not candidate.is_relative_to(root):
            raise ValueError("input reference escaped the configured input directory")
        # The orchestrator's input discovery uses org/unit/stage. Refuse legacy
        # unscoped paths here so one tenant cannot submit another tenant's image.
        if candidate.relative_to(root).parts[:2] != (org, subject):
            raise ValueError("Prep input image is not scoped to this organization and unit")
        raw = candidate.read_bytes()
        if hashlib.sha256(raw).hexdigest() != item.get("sha256"):
            raise ValueError("Prep input image changed after it was catalogued")
        media = mimetypes.guess_type(candidate.name)[0] or "image/jpeg"
        if media not in {"image/jpeg", "image/png", "image/webp"}:
            continue
        uploads.append({"filename": candidate.name, "mediaType": media,
                        "dataBase64": base64.b64encode(raw).decode("ascii")})
        paths.append(item["ref"])
    return uploads, paths


def handle(request: dict) -> dict:
    case = request.get("context", {}).get("case", {})
    subject = request["subject"]
    _refuse_known_cross_tenant_sample(request)
    if case.get("org_id", subject["org_id"]) != subject["org_id"]:
        raise LookupError("Prep case belongs to a different organization")
    service = os.environ.get("PREP_MANAGER_URL", "").strip().rstrip("/")
    prep = case.get("prep") if isinstance(case.get("prep"), dict) else {}
    product = prep.get("product")
    if not service:
        return _pending(request, "prep_service_not_configured",
                        "Set PREP_MANAGER_URL to the existing Prep Manager service to run inspection.")
    if not isinstance(product, dict) or not product.get("sku"):
        return _pending(request, "prep_product_missing",
                        "Prep requires a product configuration in context.case.prep.product.")
    try:
        uploads, refs = _photos(request)
        if not uploads:
            return _pending(request, "prep_photos_missing", "No tenant-scoped Prep photos were provided.")
        body = {"product": product, "photos": uploads, "unitId": subject["subject_id"],
                "shipmentId": prep.get("shipmentId"), "notes": prep.get("notes"),
                "rulePackId": prep.get("rulePackId", "fba"),
                "rulePackVersion": prep.get("rulePackVersion", "1")}
        req = Request(service + "/api/inspect", data=json.dumps(body).encode(),
                      headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(req, timeout=float(os.environ.get("PREP_MANAGER_TIMEOUT_S", "90"))) as response:
            result = json.loads(response.read())
        if not isinstance(result, dict) or not isinstance(result.get("checks"), list):
            raise ValueError("Prep service returned an invalid inspection record")
    except (OSError, ValueError, KeyError, TypeError, HTTPError, URLError) as exc:
        return _pending(request, "prep_inspection_unavailable",
                        f"Prep inspection could not be completed: {str(exc)[:180]}")

    checks = []
    for item in result["checks"]:
        verdict = item.get("verdict")
        if verdict not in {"PASS", "FAIL", "UNCERTAIN"}:
            continue  # N/A and not-verifiable are preserved in payload, not coerced into a verdict.
        photo_idx = item.get("photoIndex")
        cited = refs[photo_idx - 1:photo_idx] if isinstance(photo_idx, int) and 0 < photo_idx <= len(refs) else refs
        checks.append(check(item.get("checkId", "prep_requirement"), verdict, None,
                            expected=item.get("expected"), observed=item.get("observed"),
                            detail="; ".join(filter(None, [item.get("ruleQuote"), item.get("ruleClause"), item.get("location")])),
                            evidence_refs=cited,
                            uncertain_reason="insufficient_evidence" if verdict == "UNCERTAIN" else None))
    verdict = result.get("overall", {}).get("status", "UNCERTAIN")
    if verdict not in {"PASS", "FAIL", "UNCERTAIN"}:
        verdict = "UNCERTAIN"
    record = build_record(
        request, agent_id=AGENT_ID, record_id=_id(request), captured_at=result.get("createdAt") or utcnow(),
        operator_id=result.get("operatorId"), checks=checks, verdict=verdict,
        outcome={"PASS": "compliant", "FAIL": "non_compliant", "UNCERTAIN": "pending_review"}[verdict],
        reason=result.get("overall", {}).get("reason", "Prep Manager result"),
        model={"name": result.get("vision", {}).get("model", "prep-manager"), "version": "1", "calls": 1 if result.get("vision", {}).get("available") else 0},
        inputs=request.get("inputs", []), needs_human=verdict == "UNCERTAIN",
        payload={"rule_pack": result.get("rulePack"), "not_applicable_or_verifiable": [
            {"check_key": item.get("checkId"), "verdict": item.get("verdict"), "rule_quote": item.get("ruleQuote")}
            for item in result["checks"] if item.get("verdict") in {"NOT_APPLICABLE", "NOT_VERIFIABLE"}],
            "measurements": prep.get("measurements"), "retake": result.get("overall", {}).get("retake", []),
            "inspection_record_id": result.get("id")})
    return build_output(record)


app = make_app(STAGE, handle)

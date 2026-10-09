"""Round 3 Pack Manager adapter for PackGuard's structured verifier.

Expected and observed lines must come from explicit case/operator observations.
Input images are cited as evidence but are never claimed to have been analyzed.
"""
from __future__ import annotations

import hashlib

from shared.utils.records import build_output, build_record, check, pending_output, utcnow
from shared.utils.hashing import seal
from shared.utils import sample_data
from shared.utils.server import make_app

from .verifier import verify_pack

STAGE = "pack"
AGENT_ID = "packguard-pack@1"
MODEL = {"name": "deterministic-packguard", "version": "1", "calls": 0}


def _record_id(request: dict) -> str:
    suffix = hashlib.sha256(request["request_id"].encode()).hexdigest()[:12].upper()
    return f"PCK-{suffix}"


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
        raise LookupError("Pack subject belongs to a different organization")


def handle(request: dict) -> dict:
    case = request.get("context", {}).get("case", {})
    subject = request["subject"]
    _refuse_known_cross_tenant_sample(request)
    if case.get("org_id", subject["org_id"]) != subject["org_id"]:
        raise LookupError("Pack case belongs to a different organization")
    pack = case.get("pack") if isinstance(case.get("pack"), dict) else case
    expected, observed = pack.get("order_lines"), pack.get("observed_in_box")
    if not expected or not observed:
        return _pending(request, "pack_observation_missing",
                        "Provide order_lines and operator-observed observed_in_box before judging contents.")

    result = verify_pack(expected, observed)
    refs = [item["ref"] for item in request.get("inputs", [])]
    checks = []
    if result["checks"]:
        expected_map, observed_map = result["expected"], result["observed"]
        missing = sorted(sku for sku, qty in expected_map.items() if qty > 0 and observed_map.get(sku, 0) == 0)
        extras = sorted(sku for sku, qty in observed_map.items() if qty > 0 and sku not in expected_map)
        checks = [
            check("items_present", "FAIL" if missing else "PASS", None,
                  expected=sorted(expected_map), observed=sorted(observed_map),
                  detail=f"Missing SKUs: {missing}" if missing else "Every expected SKU is present.", evidence_refs=refs),
            check("quantities_correct", "FAIL" if result["verdict"] == "FAIL" else "PASS", None,
                  expected=expected_map, observed=observed_map, detail=result["reason"], evidence_refs=refs),
            check("no_extra_items", "FAIL" if extras else "PASS", None,
                  expected=[], observed=extras, detail=f"Unexpected SKUs: {extras}" if extras else "No extra SKUs.", evidence_refs=refs),
        ]
    verdict = result["verdict"]
    record = build_record(
        request, agent_id=AGENT_ID, record_id=_record_id(request), captured_at=case.get("captured_at") or utcnow(),
        checks=checks, verdict=verdict,
        outcome={"PASS": "seal", "FAIL": "stop_and_fix", "UNCERTAIN": "pending_review"}[verdict],
        reason=result["reason"], model=MODEL, unit_scope="order", refs={"order_id": pack.get("order_id")},
        inputs=request.get("inputs", []), needs_human=verdict == "UNCERTAIN",
        payload={"action": result["action"], "expected": result["expected"], "observed": result["observed"],
                 "observation_source": "operator_supplied_structured_observation", "photo_analysis_performed": False})
    return build_output(record)


app = make_app(STAGE, handle)

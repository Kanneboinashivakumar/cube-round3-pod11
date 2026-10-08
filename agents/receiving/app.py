"""DockProof Receiving Manager adapter for the Round 3 evidence contract.

The adapter keeps the Round 2 eight-check inspection model, translates it to the
shared agent-output contract, and fails closed to UNCERTAIN when visual evidence
is unavailable. Synthetic CSV fixtures are marked as fixtures and never described
as a live photo inspection.
"""
from __future__ import annotations

import hashlib
from typing import Any

from shared.utils import sample_data
from shared.utils.records import build_output, build_record, check, pending_output, utcnow
from shared.utils.server import make_app

from .vlm import inspect_images

STAGE = "receiving"
AGENT_ID = "dockproof-receiving@1"
CHECKS = (
    "identity_match", "quantity", "carton_count", "units_per_carton",
    "variant", "carton_damage", "unit_damage", "components",
)


def _verdict(value: str | None) -> str:
    return {"pass": "PASS", "fail": "FAIL", "uncertain": "UNCERTAIN"}.get(str(value or "").lower(), "UNCERTAIN")


def _photo_refs(request: dict) -> list[str]:
    return [item["ref"] for item in request.get("inputs", []) if item.get("kind") == "image"]


def _sample_observation(row: dict) -> dict:
    """Offline fixture adapter: values are synthetic CSV observations, not vision results."""
    flags = [flag.strip().lower() for flag in row.get("quality_flags", "").split(";") if flag.strip()]
    identity = {"yes": "pass", "no": "fail"}.get(row.get("identity_match", ""), "uncertain")
    carton_damage = "pass" if row.get("carton_damage") in ("", "none") else (
        "uncertain" if row.get("carton_damage") == "uncertain" else "fail")
    unit_damage = "pass" if row.get("unit_damage") in ("", "none") else (
        "uncertain" if row.get("unit_damage") == "uncertain" else "fail")
    return {
        "identity": {"verdict": identity, "confidence": .88 if identity != "uncertain" else .4,
                     "observed_sku": row.get("sku") if identity != "fail" else None,
                     "reason": "Synthetic sample CSV fixture; no photo was analyzed."},
        "quantity": {"verdict": "pass" if row.get("qty_ordered") == row.get("qty_received") else "fail",
                     "confidence": .9, "observed_quantity": int(row.get("qty_received") or 0),
                     "reason": "Synthetic sample CSV fixture; quantity was not visually counted."},
        "cartons": {"verdict": "pass" if row.get("cartons_ordered") == row.get("cartons_received") else "fail",
                    "confidence": .9, "observed_cartons": int(row.get("cartons_received") or 0),
                    "reason": "Synthetic sample CSV fixture; carton count was not visually confirmed."},
        "units_per_carton": {"verdict": "pass" if row.get("units_per_carton_ordered") == row.get("units_per_carton_counted") else "fail",
                             "confidence": .86, "observed_units_per_carton": int(row.get("units_per_carton_counted") or 0),
                             "reason": "Synthetic sample CSV fixture; count was not visually confirmed."},
        "variant": {"verdict": "fail" if any(any(term in f for term in ("wrong variant", "wrong colour", "wrong color")) for f in flags) else "pass",
                    "confidence": .84, "observed_colour": row.get("spec_colour"), "observed_variant": row.get("spec_variant"),
                    "reason": "Synthetic sample CSV fixture; variant was not visually inspected."},
        "carton_damage": {"verdict": carton_damage, "confidence": .86 if carton_damage != "uncertain" else .4,
                           "damage_type": row.get("carton_damage") or "none", "reason": "Synthetic sample CSV fixture; no carton photo was analyzed."},
        "unit_damage": {"verdict": unit_damage, "confidence": .84 if unit_damage != "uncertain" else .4,
                         "damage_type": row.get("unit_damage") or "none", "reason": "Synthetic sample CSV fixture; no product photo was analyzed."},
        "components": {"verdict": "fail" if any("missing component" in f for f in flags) else "pass",
                       "confidence": .82, "components": [{"name": name.strip(), "status": "present", "visible": False}
                                                             for name in row.get("spec_components", "").split(";") if name.strip()],
                       "reason": "Synthetic sample CSV fixture; component presence was not visually verified."},
        "metadata": {"model_version": "synthetic-csv-fixture", "latency_ms": 0},
    }


def _unknown_observation(reason: str) -> dict:
    result = {"metadata": {"model_version": "no-visual-evidence", "latency_ms": 0}}
    for key in ("identity", "quantity", "cartons", "units_per_carton", "variant", "carton_damage", "unit_damage", "components"):
        result[key] = {"verdict": "uncertain", "confidence": 0.0, "reason": reason}
    return result


def _expected(case: dict[str, Any], row: dict | None) -> dict[str, Any]:
    receiving = case.get("receiving") or {}
    def prefer(key: str, csv_key: str):
        value = receiving.get(key)
        return value if value is not None and value != "" else (row or {}).get(csv_key)
    return {
        "po_number": prefer("po_number", "po_number"),
        "po_line": prefer("po_line", "po_line"),
        "sku": prefer("sku", "sku"),
        "asin": prefer("asin", "asin"),
        "product_title": prefer("product_title", "product_title"),
        "quantity": prefer("quantity", "qty_ordered") if receiving.get("quantity") is not None else ((row or {}).get("qty_ordered") and int(row["qty_ordered"])),
        "cartons": prefer("cartons", "cartons_ordered") if receiving.get("cartons") is not None else ((row or {}).get("cartons_ordered") and int(row["cartons_ordered"])),
        "units_per_carton": prefer("units_per_carton", "units_per_carton_ordered") if receiving.get("units_per_carton") is not None else ((row or {}).get("units_per_carton_ordered") and int(row["units_per_carton_ordered"])),
        "colour": prefer("colour", "spec_colour"),
        "variant": prefer("variant", "spec_variant"),
        "components": receiving.get("components") if receiving.get("components") is not None else [v.strip() for v in (row or {}).get("spec_components", "").split(";") if v.strip()],
    }


def _build_checks(observation: dict, expected: dict, row: dict | None, photo_refs: list[str]) -> list[dict]:
    checks = []
    for key in CHECKS:
        item = observation.get({"identity_match": "identity", "carton_count": "cartons"}.get(key, key), {})
        verdict = _verdict(item.get("verdict"))
        confidence = item.get("confidence")
        exp: Any = None
        observed: Any = None
        if key == "identity_match": exp, observed = expected.get("sku"), item.get("observed_sku")
        elif key == "quantity": exp, observed = expected.get("quantity"), item.get("observed_quantity")
        elif key == "carton_count": exp, observed = expected.get("cartons"), item.get("observed_cartons")
        elif key == "units_per_carton": exp, observed = expected.get("units_per_carton"), item.get("observed_units_per_carton")
        elif key == "variant": exp, observed = {"colour": expected.get("colour"), "variant": expected.get("variant")}, {"colour": item.get("observed_colour"), "variant": item.get("observed_variant")}
        elif key == "carton_damage": exp, observed = "no visible damage", {"type": item.get("damage_type"), "severity": item.get("severity")}
        elif key == "unit_damage": exp, observed = "no visible damage", {"type": item.get("damage_type"), "severity": item.get("severity")}
        else: exp, observed = expected.get("components"), item.get("components")
        reason = item.get("reason") or "The available evidence does not support a reliable determination."
        required_expectation = {
            "identity_match": expected.get("sku"), "quantity": expected.get("quantity"),
            "carton_count": expected.get("cartons"), "units_per_carton": expected.get("units_per_carton"),
            "variant": expected.get("colour") or expected.get("variant"), "components": expected.get("components"),
        }.get(key, "known")
        if required_expectation in (None, "", []):
            verdict = "UNCERTAIN"
            reason = "The purchase-order expectation for this check was not supplied."
        checks.append(check(key, verdict, confidence if isinstance(confidence, (int, float)) else None,
                            expected=exp, observed=observed, detail=reason, evidence_refs=photo_refs,
                            uncertain_reason="missing_visual_evidence" if verdict == "UNCERTAIN" else None))
    return checks


def handle(request: dict) -> dict:
    subject = request["subject"]
    case = request.get("context", {}).get("case", {})
    row = None
    receiving_context = case.get("receiving") or {}
    has_custom_po = any(receiving_context.get(key) not in (None, "", []) for key in ("sku", "quantity", "cartons", "po_number"))
    if not has_custom_po:
        try:
            row = sample_data.row("receiving", subject["subject_id"], subject["org_id"])
        except LookupError:
            if "receiving" not in case:
                raise

    expected = _expected(case, row)
    photo_refs = _photo_refs(request)
    observation = None
    try:
        if photo_refs:
            observation = inspect_images(expected, request.get("inputs", []))
        elif row is not None:
            observation = _sample_observation(row)
        else:
            observation = _unknown_observation("No receiving photographs or observed counts were supplied.")
    except Exception as exc:
        # The contract's pending output is an explicit error/UNCERTAIN record, never an invented judgment.
        return pending_output(request, code="vision_unavailable", message=str(exc)[:240], retryable=True, agent_id=AGENT_ID)

    checks = _build_checks(observation, expected, row, photo_refs)
    verdict = "FAIL" if any(c["verdict"] == "FAIL" for c in checks) else (
        "UNCERTAIN" if any(c["verdict"] == "UNCERTAIN" for c in checks) else "PASS")
    outcome = {"PASS": "accept", "FAIL": "accept_with_exceptions", "UNCERTAIN": "pending_review"}[verdict]
    source = "Round 2 DockProof VLM" if photo_refs else "synthetic CSV adapter" if row else "unobserved receipt"
    if row:
        source_id = str(row.get("record_id") or "")
        suffix = source_id[4:] if source_id.startswith("RCV-") else source_id or hashlib.sha256(request["request_id"].encode()).hexdigest()[:12].upper()
        project_id = str(case.get("project_id") or "")
        rid = f"RCV-{project_id}-{suffix}" if project_id else f"RCV-{suffix}"
    else:
        rid = "RCV-" + hashlib.sha256(request["request_id"].encode()).hexdigest()[:12].upper()
    model = {"name": observation.get("metadata", {}).get("model_version", "dockproof-receiving"),
             "version": "round2-adapter-v1", "provider": "live-vlm" if photo_refs else "fixture-or-none",
             "calls": 1 if photo_refs else 0, "cost_usd": 0}
    reason = f"{source}; {sum(c['verdict'] == 'FAIL' for c in checks)} failed and {sum(c['verdict'] == 'UNCERTAIN' for c in checks)} uncertain checks."
    observed_quantity = observation.get("quantity", {}).get("observed_quantity")
    expected_quantity = expected.get("quantity")
    supplier_shortfall = (max(expected_quantity - observed_quantity, 0)
                          if isinstance(expected_quantity, (int, float)) and isinstance(observed_quantity, (int, float)) else None)
    record = build_record(
        request, agent_id=AGENT_ID, record_id=rid, captured_at=(row or {}).get("captured_at") or utcnow(),
        operator_id=(row or {}).get("operator_id"), unit_scope="po_line",
        refs={"po_number": expected.get("po_number"), "po_line": expected.get("po_line"), "sku": expected.get("sku"), "asin": expected.get("asin")},
        checks=checks, outcome=outcome, model=model, inputs=request.get("inputs", []), reason=reason,
        payload={"expected": expected, "supplier_shortfall_units": supplier_shortfall,
                 "quality_flags": (row or {}).get("quality_flags", ""), "evidence_source": source,
                 "model_metadata": observation.get("metadata", {})},
    )
    return build_output(record)


app = make_app(STAGE, handle)

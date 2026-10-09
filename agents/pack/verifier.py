"""Deterministic comparison of expected and operator-observed pack contents."""
from __future__ import annotations

from collections import defaultdict


def parse_lines(value: str | None) -> tuple[dict[str, int], list[str]]:
    lines: dict[str, int] = defaultdict(int)
    invalid: list[str] = []
    for raw in (value or "").split(";"):
        raw = raw.strip()
        if not raw:
            continue
        try:
            sku, quantity = raw.rsplit(":", 1)
            count = int(quantity)
        except (ValueError, AttributeError):
            invalid.append(raw)
            continue
        if sku.strip() and count >= 0:
            lines[sku.strip()] += count
        else:
            invalid.append(raw)
    return dict(lines), invalid


def verify_pack(order_lines: str | None, observed_in_box: str | None) -> dict:
    """Compare supplied structured observations; this function does not analyze photos."""
    expected, bad_expected = parse_lines(order_lines)
    observed, bad_observed = parse_lines(observed_in_box)
    if bad_expected or bad_observed:
        sources = " and ".join(name for name, bad in (("order lines", bad_expected), ("observed contents", bad_observed)) if bad)
        return {"verdict": "UNCERTAIN", "action": "HOLD_FOR_REVIEW", "reason": f"Malformed {sources} prevent a reliable comparison.", "expected": expected, "observed": observed, "checks": []}
    if not expected:
        return {"verdict": "UNCERTAIN", "action": "HOLD_FOR_REVIEW", "reason": "No valid order lines were supplied.", "expected": expected, "observed": observed, "checks": []}
    if not (observed_in_box or "").strip():
        return {"verdict": "UNCERTAIN", "action": "RECAPTURE", "reason": "No observed contents were supplied; the box cannot be judged.", "expected": expected, "observed": observed, "checks": []}
    checks = []
    for sku in sorted(set(expected) | set(observed)):
        exp, got = expected.get(sku, 0), observed.get(sku, 0)
        checks.append({"sku": sku, "expected": exp, "observed": got,
                       "verdict": "PASS" if exp == got else "FAIL",
                       "detail": f"{sku}: expected {exp}, found {got}."})
    passed = all(c["verdict"] == "PASS" for c in checks)
    return {"verdict": "PASS" if passed else "FAIL", "action": "SEAL" if passed else "STOP_AND_FIX",
            "reason": "All expected quantities match." if passed else "Contents do not match the order.",
            "expected": expected, "observed": observed, "checks": checks}

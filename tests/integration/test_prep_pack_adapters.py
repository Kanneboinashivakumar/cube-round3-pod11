import base64

from agents.pack.app import handle as pack_handle
from agents.prep.app import handle as prep_handle
from orchestration.orchestrator import applies, load_flow
from shared.utils.hashing import verify
from shared.utils.schema import errors
from fastapi.testclient import TestClient


def request(stage, case):
    return {"schema_version": "1.0", "request_id": f"WF-test:{stage}", "workflow_id": "WF-test",
            "stage": stage, "subject": {"org_id": "org_demo_alpha", "subject_id": "UNIT-test", "route": "mfn"},
            "inputs": [], "previous_evidence": [], "context": {"overrides": [], "case": case}}


def test_pack_adapter_emits_deterministic_evidence_from_structured_observations():
    req = request("pack", {"org_id": "org_demo_alpha", "pack": {
        "order_lines": "A:2;B:1", "observed_in_box": "A:2;B:1", "order_id": "ORDER-1"}})
    first, again = pack_handle(req), pack_handle(req)
    assert errors("agent-output", first) == []
    assert first["evidence"]["decision"]["verdict"] == "PASS"
    assert first["evidence"]["payload"]["photo_analysis_performed"] is False
    assert first["evidence"]["record_id"] == again["evidence"]["record_id"]
    assert verify(first["evidence"])


def test_pack_adapter_preserves_uncertainty_when_observation_missing():
    req = request("pack", {"org_id": "org_demo_alpha", "pack": {"order_lines": "A:1"}})
    req["inputs"] = [{"ref": "org_demo_alpha/UNIT-test/pack/photo.jpg", "kind": "image", "sha256": "a" * 64}]
    out = pack_handle(req)
    assert errors("agent-output", out) == []
    assert out["status"] == "pending" and out["verdict"] == "UNCERTAIN"
    assert out["evidence"]["inputs"] == req["inputs"] and verify(out["evidence"])


def test_prep_adapter_fails_open_without_configured_service(monkeypatch):
    monkeypatch.delenv("PREP_MANAGER_URL", raising=False)
    req = request("prep", {"org_id": "org_demo_alpha", "prep": {"product": {"sku": "A"}}})
    req["inputs"] = [{"ref": "org_demo_alpha/UNIT-test/prep/photo.jpg", "kind": "image", "sha256": "b" * 64}]
    out = prep_handle(req)
    assert errors("agent-output", out) == []
    assert out["status"] == "pending" and out["verdict"] == "UNCERTAIN"
    assert out["evidence"]["inputs"] == req["inputs"] and verify(out["evidence"])


def test_cube_flow_routes_only_to_applicable_lifecycle_stages():
    flow = load_flow("orchestration/projects/cube/flow.json")
    stages = {step["stage"]: step for step in flow["steps"]}
    fba = {"route": "fba", "returned": False, "has_charge": False}
    mfn = {"route": "mfn", "returned": True, "has_charge": True}
    assert applies(stages["prep"], fba)[0] and not applies(stages["pack"], fba)[0]
    assert applies(stages["pack"], mfn)[0] and not applies(stages["prep"], mfn)[0]
    assert applies(stages["returns"], mfn)[0] and applies(stages["recovery"], mfn)[0]


def test_cube_events_advance_route_return_and_charge_stages(monkeypatch, tmp_path):
    from orchestration import api
    from orchestration.store import FileStore

    monkeypatch.setattr(api, "STORE", FileStore(tmp_path))
    monkeypatch.setenv("PREP_MANAGER_URL", "")
    monkeypatch.setenv("INPUT_DIR", str(tmp_path / "captures"))
    client = TestClient(api.app)
    base = {"project_id": "cube", "org_id": "org_demo_alpha", "unit_id": "UNIT-EVENT-TEST",
            "route": "fba", "receiving": {"sku": "SKU-1", "quantity": 1},
            "prep": {"product": {"sku": "SKU-1", "expectedFnsku": "FNSKU-1", "name": "Item",
                                   "category": "general", "requiresPolybag": False, "hasExpiry": False,
                                   "isFragile": False, "requiredHandlingMarks": [], "coverOriginalBarcode": False},
                      "photos": [{"mime_type": "image/jpeg", "data": base64.b64encode(b"\xff\xd8\xfftest").decode()}]},
            "pack": {"order_lines": "SKU-1:1", "observed_in_box": "SKU-1:1"}}
    receipt = client.post("/events", json={**base, "event_type": "PRODUCT_RECEIVED"})
    assert receipt.status_code == 200, receipt.text
    workflow = receipt.json()
    states = {item["stage"]: item["state"] for item in workflow["stage_results"]}
    assert states["prep"] == "error" and states["pack"] == "skipped"
    assert workflow["context"]["prep"]["product"]["sku"] == "SKU-1"
    assert list((tmp_path / "captures" / "org_demo_alpha" / "UNIT-EVENT-TEST" / "prep").glob("*.jpg"))
    prep_record = api.STORE.get_evidence(next(item["record_id"] for item in workflow["stage_results"] if item["stage"] == "prep"))
    assert prep_record["inputs"][0]["ref"].startswith("org_demo_alpha/UNIT-EVENT-TEST/prep/")
    assert states["returns"] == states["recovery"] == "skipped"

    merchant = client.post("/events", json={**base, "unit_id": "UNIT-MFN-TEST", "route": "mfn",
                                              "event_type": "PRODUCT_RECEIVED"})
    assert merchant.status_code == 200, merchant.text
    merchant_workflow = merchant.json()
    assert next(item for item in merchant_workflow["stage_results"] if item["stage"] == "pack")["verdict"] == "PASS"
    assert next(item for item in merchant_workflow["stage_results"] if item["stage"] == "prep")["state"] == "skipped"

    client.post("/events", json={**base, "event_type": "RETURN_INITIATED"}).raise_for_status()
    returned = client.post("/events", json={**base, "event_type": "RETURN_RECEIVED"})
    assert returned.status_code == 200, returned.text
    assert next(item for item in returned.json()["stage_results"] if item["stage"] == "returns")["state"] != "skipped"

    charged = client.post("/events", json={**base, "event_type": "CHARGE_RECEIVED", "fee": {"amount_usd": 4.5}})
    assert charged.status_code == 200, charged.text
    assert next(item for item in charged.json()["stage_results"] if item["stage"] == "recovery")["state"] != "skipped"


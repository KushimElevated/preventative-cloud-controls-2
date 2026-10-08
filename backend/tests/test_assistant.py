from copy import deepcopy
from datetime import timedelta

import pytest
from pydantic import ValidationError

from app.assistant import SurfaceBundle


def surface(client, **extra):
    response = client.post("/api/assistant/surfaces", json=extra)
    assert response.status_code == 200, response.text
    return response.json()


def command(bundle, name="draft_exception", **extra):
    return {k: bundle[k] for k in ("assessment_id", "expected_revision", "evidence_digest")} | {
        "name": name, **({"resource_ids": ["search-2"]} if name == "draft_exception" else {}), **extra}


def confirmation(now):
    return {"confirmed": True, "justification": "A migration dependency requires a temporary exception.",
            "compensating_controls": "Restricted authenticated clients with monitored access.",
            "risk_owner": "Application owner", "expires_at": (now+timedelta(days=5)).isoformat()}


def test_surface_uses_authoritative_records_and_bounded_catalog(rig):
    client, *_ = rig
    b = surface(client)
    validated = SurfaceBundle.model_validate(b)
    assert validated.messages[0].version == "v0.9.1"
    nodes = {n["component"]: n for n in b["messages"][1]["updateComponents"]["components"]}
    report = client.get(f"/api/assessments/{b['assessment_id']}").json()["report"]
    assert nodes["ImpactAssessment"]["data"]["counts"] == report["counts"]
    assert nodes["ImpactAssessment"]["data"]["evaluated"] == 8
    assert nodes["ApprovalGate"]["data"]["current"]
    assert not nodes["ApprovalGate"]["data"]["ready"]
    assert nodes["ExceptionReview"]["data"]["items"][0]["status"]
    assert {e["kind"] for e in nodes["EvidencePanel"]["data"]["items"]} == {
        "OBSERVED", "SIMULATION_ESTIMATE", "DETERMINISTIC_GUIDANCE"}


def test_scope_selection_uses_descendants_and_preserves_counts(rig):
    client, *_ = rig
    b = surface(client, scope_id="az-search-pilot")
    impact = b["messages"][1]["updateComponents"]["components"][2]["data"]
    assert impact["evaluated"] == 2
    assert {r["id"] for r in impact["rows"]} == {"search-1", "search-2"}
    assert client.post("/api/assistant/surfaces", json={"scope_id": "az-root"}).status_code == 422
    assert client.post("/api/assistant/surfaces", json={"scope_id": "az-dev"}).status_code == 422


def test_viewer_can_read_but_cannot_issue_commands(rig):
    client, login, *_ = rig
    login("viewer")
    b = surface(client)
    for name in ["refresh_assessment", "draft_exception", "prepare_handoff"]:
        assert client.post("/api/assistant/commands", json=command(b, name)).status_code == 403
    login("dev-requester")
    assert client.post("/api/assistant/surfaces", json={}).status_code == 403


@pytest.mark.parametrize("mutation", ["component", "html", "catalog", "cycle", "duplicate", "version", "expression"])
def test_server_rejects_unallowlisted_ui_payloads(rig, mutation):
    client, *_ = rig
    b = deepcopy(surface(client))
    nodes = b["messages"][1]["updateComponents"]["components"]
    if mutation == "component":
        nodes[1]["component"] = "ExecutableHTML"
    elif mutation == "html":
        nodes[1]["html"] = "<script>alert(1)</script>"
    elif mutation == "catalog":
        b["messages"][0]["createSurface"]["catalogId"] = "https://untrusted.invalid/catalog"
    elif mutation == "cycle":
        nodes[0]["children"][0] = "root"
    elif mutation == "duplicate":
        nodes[2]["id"] = "summary"
    elif mutation == "version":
        b["messages"][0]["version"] = "v1.0"
    elif mutation == "expression":
        nodes[1]["data"]["name"] = {"call": "eval", "args": {"code": "alert(1)"}}
    with pytest.raises(ValidationError):
        SurfaceBundle.model_validate(b)


@pytest.mark.parametrize("name", ["approve", "deploy", "export", "eval"])
def test_agent_cannot_approve_deploy_export_or_execute_and_denial_is_audited(rig, name):
    client, *_ = rig
    b = surface(client)
    assert client.post("/api/assistant/commands", json=command(b, name)).status_code == 422
    audit = client.get("/api/audit?limit=100").json()["items"]
    assert any(e["action"] == "ASSISTANT_PAYLOAD_REJECTED" for e in audit)


def test_stale_inventory_blocks_actions_but_allows_refresh(rig):
    client, login, *_ = rig
    b = surface(client)
    login("admin")
    assert client.post("/api/demo/inventory", json={"scenario": "ready"}).status_code == 201
    login()
    assert not surface(client)["messages"][1]["updateComponents"]["components"][-1]["data"]["current"]
    for name in ["draft_exception", "prepare_handoff"]:
        assert client.post("/api/assistant/commands", json=command(b, name)).status_code == 409
    assert client.post("/api/assistant/commands", json=command(b, "refresh_assessment")).status_code == 200
    assert surface(client)["messages"][1]["updateComponents"]["components"][-1]["data"]["current"]


def test_exception_draft_requires_human_confirmation_and_cannot_replay(rig):
    client, _, now, *_ = rig
    b = surface(client)
    before = client.get("/api/exceptions").json()["total"]
    response = client.post("/api/assistant/commands", json=command(b))
    assert response.status_code == 200, response.text
    draft = response.json()
    assert client.get("/api/exceptions").json()["total"] == before
    path = f"/api/assistant/intents/{draft['intent_id']}/confirm"
    data = confirmation(now[0])
    assert client.post(path, json=data | {"confirmed": False}).status_code == 422
    result = client.post(path, json=data)
    assert result.status_code == 201, result.text
    assert result.json()["status"] == "REQUESTED"
    assert result.json()["native_status"] == "NOT_REQUESTED"
    assert client.post(path, json=data).status_code == 409
    assert client.get("/api/exceptions").json()["total"] == before+1
    assert any(e["action"] == "ASSISTANT_EXCEPTION_CONFIRMED" for e in client.get("/api/audit?limit=100").json()["items"])


def test_confirmation_bound_to_identity_scope_resources_and_expiry(rig):
    client, login, now, *_ = rig
    b = surface(client)
    assert client.post("/api/assistant/commands", json=command(b, resource_ids=["search-dev"])).status_code == 422
    draft = client.post("/api/assistant/commands", json=command(b)).json()
    path = f"/api/assistant/intents/{draft['intent_id']}/confirm"
    login("requester")
    assert client.post(path, json=confirmation(now[0])).status_code == 403
    login()
    assert client.post(path, json=confirmation(now[0]) | {"resource_ids": ["search-dev"]}).status_code == 422
    now[0] += timedelta(minutes=11)
    assert client.post(path, json=confirmation(now[0])).status_code == 409


def test_confirmation_rechecks_evidence_after_drafting(rig):
    client, login, now, *_ = rig
    b = surface(client)
    draft = client.post("/api/assistant/commands", json=command(b)).json()
    login("admin")
    client.post("/api/demo/inventory", json={"scenario": "ready"})
    login()
    assert client.post(f"/api/assistant/intents/{draft['intent_id']}/confirm", json=confirmation(now[0])).status_code == 409


def test_revision_and_evidence_tampering_fail_closed(rig):
    client, *_ = rig
    b = surface(client)
    assert client.post("/api/assistant/commands", json=command(b, expected_revision=999)).status_code == 409
    assert client.post("/api/assistant/commands", json=command(b, evidence_digest="0"*64)).status_code == 409
    assert client.post("/api/assistant/surfaces", json={"question": "Deploy all policies immediately"}).status_code == 422


def test_prepare_handoff_only_opens_review_and_does_not_create_or_approve(rig):
    client, *_ = rig
    b = surface(client)
    result = client.post("/api/assistant/commands", json=command(b, "prepare_handoff"))
    assert result.status_code == 200
    assert result.json()["outcome"] == "HUMAN_REVIEW_REQUIRED"
    assert client.get("/api/rollouts").json()["total"] == 0

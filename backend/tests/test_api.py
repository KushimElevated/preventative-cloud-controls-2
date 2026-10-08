from datetime import timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.models import AuditEvent, User
from app.seed import seed
from conftest import approved_plan, ready_plan


def receipt_payload(obj, now, status="VERIFIED", event="demo-event-1"):
    return {"event_id": event, "manifest_digest": obj["manifest_digest"], "scope_id": obj["manifest"]["scope_id"],
            "implementation_digest": obj["manifest"]["implementation_digest"], "observed_at": now.isoformat(),
            "status": status, "provenance": "DEMO"}


def test_seed_idempotent_and_schema(rig):
    client, _, now, sessions, _ = rig
    with sessions.begin() as db:
        assert not seed(db, now[0])
    assert client.get("/health").json()["live_deployment"] is False
    assert client.get("/api/controls").json()["total"] == 2
    assert client.get("/openapi.json").status_code == 200


def test_unauthenticated_cannot_read(rig):
    client, *_ = rig
    client.headers.pop("Authorization")
    assert client.get("/api/controls").status_code == 401


def test_client_cannot_supply_role(rig):
    client, login, *_ = rig
    login("viewer")
    client.headers["X-Role"] = "CONTROL_ENGINEER"
    assert client.post("/api/controls/azure-search/assessments", json={"scope_id": "az-prod"}).status_code == 403


def test_scope_read_write_isolation(rig):
    client, login, *_ = rig
    login("dev-requester")
    assert client.get("/api/controls").json()["items"] == []
    assert client.get("/api/controls/azure-search").status_code == 403
    assert all(r["scope_id"] == "az-dev" for r in client.get("/api/inventory").json()["resources"])
    assert client.get("/api/exceptions").json()["items"] == []


def test_baseline_assessment_is_honest(rig):
    client, *_ = rig
    response = client.post("/api/controls/azure-search/assessments", json={"scope_id": "az-prod"})
    assert response.status_code == 201, response.text
    report = response.json()["report"]
    assert report["counts"]["NON_COMPLIANT"] == 5
    states = {r["id"]: r["exception"] for r in report["rows"]}
    assert states["search-3"] == "PENDING"
    assert states["search-4"] == "APPROVED_UNAPPLIED"
    assert states["search-5"] == "EFFECTIVE"
    assert states["search-6"] == "EXPIRED"


def test_export_requires_approval_and_pilot(rig):
    client, *_ = rig
    obj = ready_plan(rig)
    assert client.post(f"/api/rollouts/{obj['id']}/export").status_code == 409
    assert client.post(f"/api/rollouts/{obj['id']}/export?draft=true").json()["status"] == "DRAFT_UNAPPROVED"
    assert client.get(f"/api/rollouts/{obj['id']}").json()["delivery_state"] == "NOT_EXPORTED"


def test_full_azure_path_and_duplicate_receipts(rig):
    client, login, now, *_ = rig
    obj, bundle = approved_plan(rig)
    assert bundle["status"] == "APPROVED_DEMO_HANDOFF"
    assert bundle["artifacts"]["execute"] is False
    assert client.get("/api/dashboard").json()["protected_pairs"] == 0
    login("cloud")
    payload = receipt_payload(obj, now[0])
    path = f"/api/rollouts/{obj['id']}/mock-receipts"
    first = client.post(path, json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["disposition"] == "VERIFIED"
    assert client.post(path, json=payload).json()["id"] == first.json()["id"]
    assert len(client.get(f"/api/rollouts/{obj['id']}/receipts").json()) == 1
    metrics = client.get("/api/dashboard").json()
    assert metrics["applicable_pairs"] == 10
    assert metrics["protected_pairs"] == 6
    assert metrics["exempt_pairs"] == 1
    assert metrics["denied_runtime_operations"] is None


@pytest.mark.parametrize("field,value", [("manifest_digest", "0"*64), ("scope_id", "az-dev")])
def test_mismatched_receipt_cannot_verify(rig, field, value):
    client, login, now, *_ = rig
    obj, _ = approved_plan(rig)
    login("cloud")
    payload = receipt_payload(obj, now[0])
    payload[field] = value
    r = client.post(f"/api/rollouts/{obj['id']}/mock-receipts", json=payload)
    assert r.json()["disposition"] == "MISMATCHED"
    assert client.get(f"/api/rollouts/{obj['id']}").json()["delivery_state"] == "EXPORTED"


def test_stale_and_drift_receipts(rig):
    client, login, now, *_ = rig
    obj, _ = approved_plan(rig)
    login("cloud")
    path = f"/api/rollouts/{obj['id']}/mock-receipts"
    assert client.post(path, json=receipt_payload(obj, now[0])).json()["disposition"] == "VERIFIED"
    old = receipt_payload(obj, now[0]-timedelta(minutes=1), "FAILED", "old-event")
    assert client.post(path, json=old).json()["disposition"] == "STALE"
    assert client.get(f"/api/rollouts/{obj['id']}").json()["delivery_state"] == "VERIFIED"
    now[0] += timedelta(minutes=1)
    drift = receipt_payload(obj, now[0], event="new-drift")
    drift["implementation_digest"] = "f"*64
    assert client.post(path, json=drift).json()["disposition"] == "DRIFTED"
    assert client.get("/api/dashboard").json()["protected_pairs"] == 0


def test_new_snapshot_invalidates_existing_approvals(rig):
    client, login, now, *_ = rig
    obj, _ = approved_plan(rig)
    now[0] += timedelta(seconds=1)
    login("admin")
    client.post("/api/demo/inventory", json={"scenario": "ready"})
    login("engineer")
    r = client.post(f"/api/rollouts/{obj['id']}/export")
    assert r.status_code == 409 and "snapshot" in r.text


def test_expiry_is_effective_without_scheduler(rig):
    client, login, now, *_ = rig
    now[0] += timedelta(days=26)
    login("viewer")
    data = client.get("/api/exceptions").json()["items"]
    assert next(e for e in data if e["id"] == "exception-effective")["disposition"] == "EXPIRED"
    login("admin")
    assert client.post("/api/reconcile").json()["cloud_mutations"] == 0
    assert client.post("/api/reconcile").json()["expired"] == []


def test_revision_invalidates_package(rig):
    client, login, *_ = rig
    obj, _ = approved_plan(rig)
    login("engineer")
    c = client.get("/api/controls/azure-search").json()
    payload = {k: c[k] for k in ["name", "objective", "rationale", "severity", "security_owner", "engineering_owner", "evidence", "scope_id"]}
    payload.update(template_id=c["implementation"]["template_id"], expected_revision=1, change_reason="Updated the scope rationale.")
    assert client.post("/api/controls/azure-search/revisions", json=payload).status_code == 201
    assert client.post(f"/api/rollouts/{obj['id']}/export").status_code == 409
    assert client.post("/api/controls/azure-search/revisions", json=payload).status_code == 409


def test_cannot_self_approve_even_after_role_change(rig):
    client, login, _, sessions, _ = rig
    obj = ready_plan(rig)
    with sessions.begin() as db:
        db.get(User, "engineer").role = "SECURITY_APPROVER"
    login("engineer")
    response = client.post(f"/api/rollouts/{obj['id']}/approvals", json={"decision": "APPROVED",
        "reason": "Attempted own approval.", "expected_version": obj["version"]})
    assert response.status_code == 403


def test_unsupported_exception_cannot_be_approved(rig):
    client, login, *_ = rig
    login("security")
    path = "/api/exceptions/exception-unsupported/decision"
    response = client.post(path, json={"decision": "REVIEW", "reason": "Review requested exception.", "expected_version": 1})
    assert response.status_code == 200, response.text
    response = client.post(path, json={"decision": "APPROVE", "reason": "Attempt an impossible exception.", "expected_version": response.json()["version"]})
    assert response.status_code == 409


def test_audit_is_not_mutable(rig):
    _, _, _, sessions, engine = rig
    with sessions() as db:
        event_id = db.scalar(select(AuditEvent.id).limit(1))
    with pytest.raises(DBAPIError):
        with engine.begin() as conn:
            conn.execute(text("UPDATE audit_events SET action='tampered' WHERE id=:id"), {"id": event_id})
    with pytest.raises(DBAPIError):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM audit_events WHERE id=:id"), {"id": event_id})


def test_body_limit_and_extra_input(rig):
    client, *_ = rig
    assert client.post("/api/auth/demo", json={"user_id": "engineer", "role": "ADMIN"}).status_code == 422
    assert client.post("/api/auth/demo", content="a"*70000).status_code == 413


def test_cross_scope_assessment_rejected(rig):
    client, *_ = rig
    assert client.post("/api/controls/azure-search/assessments", json={"scope_id": "az-root"}).status_code == 422


def test_pilot_does_not_shrink_coverage_denominator(rig):
    client, *_ = rig
    result = client.post("/api/controls/aws-s3/assessments", json={"scope_id": "aws-account-a"})
    assert result.status_code == 201, result.text
    assert result.json()["report"]["ready"]
    assert client.get("/api/dashboard").json()["applicable_pairs"] == 10


def test_no_live_deployment_route(rig):
    client, *_ = rig
    assert client.post("/api/deploy").status_code == 404


def test_exception_review_then_native_application(rig):
    client, login, *_ = rig
    login("security")
    path = "/api/exceptions/exception-pending/decision"
    result = client.post(path, json={"decision": "REVIEW", "reason": "Review migration dependency and expiry.", "expected_version": 1})
    assert result.status_code == 200, result.text
    result = client.post(path, json={"decision": "APPROVE", "reason": "Accept scoped risk with compensating controls.", "expected_version": result.json()["version"]})
    assert result.status_code == 200, result.text
    assert result.json()["disposition"] == "APPROVED_UNAPPLIED"
    login("cloud")
    result = client.post("/api/exceptions/exception-pending/mock-native-receipt", json={"status": "APPLIED",
        "reference": "mock:azure/search/assignment/exception-pending", "expected_version": result.json()["version"]})
    assert result.status_code == 200, result.text
    assert result.json()["disposition"] == "EFFECTIVE"


def test_paused_rollout_cannot_export_or_receive(rig):
    client, login, now, *_ = rig
    obj, _ = approved_plan(rig)
    obj = client.get(f"/api/rollouts/{obj['id']}").json()
    result = client.post(f"/api/rollouts/{obj['id']}/transition", json={"stage": "PAUSED", "expected_version": obj["version"]})
    assert result.status_code == 200, result.text
    assert client.post(f"/api/rollouts/{obj['id']}/export").status_code == 409
    login("cloud")
    assert client.post(f"/api/rollouts/{obj['id']}/mock-receipts", json=receipt_payload(obj, now[0])).status_code == 409

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from app.config import Settings
from app.domain import (AWS_TEMPLATE, AZURE_TEMPLATE, AwsScpProvider, AzurePolicyProvider, DomainError,
                        assess, authorize, digest, exception_disposition, fresh)
from app.seed import fixtures


NOW = datetime(2026, 10, 8, tzinfo=timezone.utc)


def test_digest_order_independent():
    assert digest({"b": 1, "a": 2}) == digest({"a": 2, "b": 1})


@pytest.mark.parametrize("live,env", [(True, "local"), (False, "production"), (False, "staging")])
def test_cannot_enable_live_or_nonlocal_auth(live, env):
    with pytest.raises(RuntimeError):
        Settings(live_deployment=live, app_env=env).validate()


def test_no_scp_audit():
    doc = deepcopy(AWS_TEMPLATE)
    doc["Statement"][0]["Effect"] = "Audit"
    with pytest.raises(DomainError):
        AwsScpProvider().validate_implementation(doc)


def test_custom_policy_is_not_silently_evaluated():
    doc = deepcopy(AZURE_TEMPLATE)
    doc["parameters"]["effect"]["value"] = "Disabled"
    with pytest.raises(DomainError):
        AzurePolicyProvider().validate_implementation(doc)


def test_configuration_and_request_counts_are_distinct():
    resources, requests = fixtures()
    report = assess(AzurePolicyProvider(), AZURE_TEMPLATE, resources, [], requests, {"az-prod"}, NOW)
    assert report["evaluated"] == sum(report["counts"].values()) == 8
    assert report["counts"] == {"COMPLIANT": 1, "NON_COMPLIANT": 5, "UNKNOWN": 1, "NOT_APPLICABLE": 1}
    assert report["predicted_denied"] == 1
    assert len(report["blockers"]) > 0
    assert report["confidence"] == "FIXTURE_ONLY"


def test_missing_requests_are_unknown_not_zero():
    resources, _ = fixtures()
    assert assess(AzurePolicyProvider(), AZURE_TEMPLATE, resources, [], [], {"az-prod"}, NOW)["predicted_denied"] is None


@pytest.mark.parametrize("status,native,days,want", [("REQUESTED", "NOT_REQUESTED", 1, "PENDING"),
    ("APPROVED", "PENDING", 1, "APPROVED_UNAPPLIED"), ("APPROVED", "APPLIED", 1, "EFFECTIVE"),
    ("APPROVED", "APPLIED", -1, "EXPIRED"), ("REVOKED", "APPLIED", 1, "REVOKED")])
def test_exception_dispositions(status, native, days, want):
    assert exception_disposition({"status": status, "native_status": native, "expires_at": (NOW+timedelta(days=days)).isoformat()}, NOW) == want


def test_aws_configuration_is_a_prerequisite_not_an_scp_side_effect():
    resources, requests = fixtures()
    report = assess(AwsScpProvider(), AWS_TEMPLATE, resources, [], requests, {"aws-account-a", "aws-account-b"}, NOW)
    assert report["counts"]["COMPLIANT"] == 1
    assert report["counts"]["NON_COMPLIANT"] == 1
    assert report["counts"]["UNKNOWN"] == 1
    assert not report["ready"]
    assert report["requests"][1]["result"] == "UNKNOWN"


def test_admin_is_not_an_approver():
    with pytest.raises(DomainError):
        authorize("ADMIN", "security_approve")


def test_future_evidence_is_not_fresh():
    assert not fresh(NOW+timedelta(minutes=1), NOW)


def test_empty_scope_is_not_ready():
    assert not assess(AzurePolicyProvider(), AZURE_TEMPLATE, [], [], [], {"az-prod"}, NOW)["ready"]

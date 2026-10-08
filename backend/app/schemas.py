from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Login(Input):
    user_id: str = Field(min_length=1, max_length=80)


class ControlInput(Input):
    name: str = Field(min_length=5, max_length=160)
    objective: str = Field(min_length=15, max_length=3000)
    rationale: str = Field(min_length=10, max_length=3000)
    severity: Literal["HIGH", "MEDIUM", "LOW"] = "HIGH"
    security_owner: str = Field(min_length=2, max_length=160)
    engineering_owner: str = Field(min_length=2, max_length=160)
    evidence: str = Field(min_length=5, max_length=3000)
    change_reason: str = Field(min_length=5, max_length=1000)
    template_id: str = Field(max_length=80)
    scope_id: str = Field(max_length=80)
    document: dict | None = None


class RevisionInput(ControlInput):
    expected_revision: int = Field(ge=1)


class AssessmentInput(Input):
    scope_id: str = Field(max_length=80)


class ExceptionInput(Input):
    control_id: str = Field(max_length=80)
    scope_id: str = Field(max_length=80)
    resource_ids: list[str] = Field(min_length=1, max_length=50)
    justification: str = Field(min_length=15, max_length=3000)
    compensating_controls: str = Field(min_length=10, max_length=3000)
    risk_owner: str = Field(min_length=3, max_length=160)
    expires_at: AwareDatetime
    renewal_of: str | None = Field(default=None, max_length=80)


class ExceptionDecision(Input):
    decision: Literal["REVIEW", "APPROVE", "REJECT", "REVOKE"]
    reason: str = Field(min_length=10, max_length=2000)
    expected_version: int = Field(ge=1)


class NativeException(Input):
    status: Literal["APPLIED", "REMOVED", "FAILED"]
    reference: str = Field(min_length=10, max_length=600)
    expected_version: int = Field(ge=1)


class RolloutInput(Input):
    assessment_id: str = Field(max_length=80)
    rollback: str = Field(min_length=30, max_length=4000)
    reason: str = Field(min_length=10, max_length=2000)


class ApprovalInput(Input):
    decision: Literal["APPROVED", "REJECTED"]
    reason: str = Field(min_length=10, max_length=2000)
    expected_version: int = Field(ge=1)


class TransitionInput(Input):
    stage: Literal["OBSERVATION", "PILOT", "LIMITED", "BROAD", "PAUSED", "CANCELLED"]
    expected_version: int = Field(ge=1)


class ReceiptInput(Input):
    event_id: str = Field(min_length=5, max_length=80)
    manifest_digest: str = Field(min_length=64, max_length=64)
    scope_id: str = Field(max_length=80)
    observed_at: AwareDatetime
    status: Literal["APPLIED", "VERIFIED", "FAILED", "DRIFTED"]
    implementation_digest: str = Field(min_length=64, max_length=64)
    provenance: Literal["DEMO"] = "DEMO"


class DemoSnapshotInput(Input):
    scenario: Literal["baseline", "ready"]

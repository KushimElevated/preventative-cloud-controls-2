"""Bounded A2UI presentation and commands over the existing authorized domain services.

The planner selects an intent; it never supplies metrics, permissions or executable UI.
Only this hydration layer constructs surfaces from persisted domain evidence.
"""
import json
from datetime import timedelta
from typing import Annotated, Literal, Protocol
from uuid import uuid4

from pydantic import AwareDatetime, Field, TypeAdapter, model_validator
from sqlalchemy import select

from . import models as m
from .domain import DomainError, PERMISSIONS, aware, descendants, digest, in_scope
from .schemas import Input, ExceptionInput

VERSION = "v0.9.1"
CATALOG = "urn:cloud-control:engineering-catalog:1"
QUESTION = "What would happen if we prevented public network access for Azure AI Search in production?"
Text = Annotated[str, Field(max_length=5000)]
Key = Annotated[str, Field(min_length=1, max_length=100)]


class SurfaceQuery(Input):
    question: str = Field(default=QUESTION, min_length=5, max_length=1000)
    control_id: Key = "azure-search"
    scope_id: Key = "az-prod"


class IntentPlanner(Protocol):
    """Future AI adapters may return this intent only, with no service/tool authority."""
    def plan(self, question: str) -> Literal["ASSESS_AZURE_SEARCH"]: ...


class DeterministicPlanner:
    def plan(self, question):
        q = question.lower()
        if not ("search" in q and ("azure" in q or "public" in q)):
            raise DomainError("This deterministic workspace supports Azure AI Search public-access assessment. Try the example question.", 422)
        return "ASSESS_AZURE_SEARCH"


class Choice(Input):
    id: Key
    label: Text


class Resource(Input):
    id: Key
    name: Text
    application: Text
    owner: Text | None
    result: Literal["COMPLIANT", "NON_COMPLIANT", "UNKNOWN", "NOT_APPLICABLE"]
    reason: Text
    exception: Text
    readiness_result: Literal["READY", "BLOCKED", "NOT_APPLICABLE"]


class Counts(Input):
    COMPLIANT: int = Field(ge=0)
    NON_COMPLIANT: int = Field(ge=0)
    UNKNOWN: int = Field(ge=0)
    NOT_APPLICABLE: int = Field(ge=0)


class SummaryData(Input):
    control_id: Key
    name: Text
    objective: Text
    revision: int = Field(ge=1)
    severity: Text
    scope_name: Text


class ImpactData(Input):
    assessment_id: Key
    scope_id: Key
    scopes: list[Choice] = Field(max_length=100)
    evaluated: int = Field(ge=0)
    counts: Counts
    rows: list[Resource] = Field(max_length=100)
    predicted_denied: int | None = Field(ge=0)
    requests_total: int = Field(ge=0)
    applications: list[Text] = Field(max_length=100)


class Baseline(Input):
    id: Key
    scope_id: Key
    effect: Text
    observed_at: Text


class PolicyData(Input):
    baseline: list[Baseline] = Field(max_length=100)
    proposed_document: str = Field(max_length=12000)
    implementation_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    limitation: Text


class ExceptionItem(Input):
    id: Key
    resource_ids: list[Key] = Field(max_length=50)
    status: Text
    disposition: Text
    expires_at: Text


class ExceptionData(Input):
    items: list[ExceptionItem] = Field(max_length=100)
    request_options: list[Choice] = Field(max_length=100)


class EvidenceItem(Input):
    label: Text
    detail: Text
    kind: Literal["OBSERVED", "SIMULATION_ESTIMATE", "DETERMINISTIC_GUIDANCE", "AI_SUGGESTION"]


class EvidenceData(Input):
    snapshot_id: Key
    assessed_at: Text
    collected_at: Text
    items: list[EvidenceItem] = Field(max_length=100)
    blockers: list[Text] = Field(max_length=200)


class RolloutItem(Input):
    id: Key
    stage: Text
    delivery_state: Text


class RolloutData(Input):
    ready: bool
    existing: list[RolloutItem] = Field(max_length=100)
    next_steps: list[Text] = Field(max_length=10)


class GateData(Input):
    current: bool
    ready: bool
    stale_reasons: list[Text] = Field(max_length=30)
    can_assess: bool
    can_request: bool
    can_plan: bool


class Workspace(Input):
    id: Literal["root"]
    component: Literal["EngineeringWorkspace"]
    children: list[Key] = Field(min_length=7, max_length=7)


class ControlSummary(Input):
    id: Literal["summary"]
    component: Literal["ControlSummary"]
    data: SummaryData


class ImpactAssessment(Input):
    id: Literal["impact"]
    component: Literal["ImpactAssessment"]
    data: ImpactData


class PolicyDiffViewer(Input):
    id: Literal["policy"]
    component: Literal["PolicyDiffViewer"]
    data: PolicyData


class ExceptionReview(Input):
    id: Literal["exceptions"]
    component: Literal["ExceptionReview"]
    data: ExceptionData


class EvidencePanel(Input):
    id: Literal["evidence"]
    component: Literal["EvidencePanel"]
    data: EvidenceData


class RolloutTimeline(Input):
    id: Literal["rollout"]
    component: Literal["RolloutTimeline"]
    data: RolloutData


class ApprovalGate(Input):
    id: Literal["gate"]
    component: Literal["ApprovalGate"]
    data: GateData


Component = Annotated[Workspace | ControlSummary | ImpactAssessment | PolicyDiffViewer |
                      ExceptionReview | EvidencePanel | RolloutTimeline | ApprovalGate,
                      Field(discriminator="component")]
COMPONENT_SCHEMA = TypeAdapter(Component)
CHILDREN = ["summary", "impact", "policy", "evidence", "exceptions", "rollout", "gate"]


class CreateSurface(Input):
    surfaceId: Key
    catalogId: Literal["urn:cloud-control:engineering-catalog:1"]


class CreateMessage(Input):
    version: Literal["v0.9.1"]
    createSurface: CreateSurface


class UpdateComponents(Input):
    surfaceId: Key
    components: list[Component] = Field(min_length=8, max_length=8)


class UpdateMessage(Input):
    version: Literal["v0.9.1"]
    updateComponents: UpdateComponents


class SurfaceBundle(Input):
    mode: Literal["DETERMINISTIC"]
    surface_id: Key
    assessment_id: Key
    expected_revision: int = Field(ge=1)
    evidence_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    messages: tuple[CreateMessage, UpdateMessage]

    @model_validator(mode="after")
    def topology(self):
        create, update = self.messages
        if create.createSurface.surfaceId != self.surface_id or update.updateComponents.surfaceId != self.surface_id:
            raise ValueError("Surface identifiers must agree")
        nodes = update.updateComponents.components
        if [n.id for n in nodes] != ["root", *CHILDREN] or nodes[0].children != CHILDREN:
            raise ValueError("Only the bounded engineering workspace topology is allowed")
        return self


class Command(Input):
    name: Literal["refresh_assessment", "draft_exception", "prepare_handoff"]
    assessment_id: Key
    expected_revision: int = Field(ge=1)
    evidence_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    resource_ids: list[Key] = Field(default_factory=list, max_length=50)


class HumanConfirmation(Input):
    confirmed: Literal[True]
    justification: str = Field(min_length=15, max_length=3000)
    compensating_controls: str = Field(min_length=10, max_length=3000)
    risk_owner: str = Field(min_length=3, max_length=160)
    expires_at: AwareDatetime


def evidence_digest(assessment):
    return digest({k: assessment[k] for k in ["id", "revision_id", "snapshot_id", "scope_id", "context", "report"]})


def render(svc, query: SurfaceQuery, planner: IntentPlanner | None = None):
    svc.permission("read")
    # The optional planner has no database, credentials, command or confirmation tools.
    if (planner or DeterministicPlanner()).plan(query.question) != "ASSESS_AZURE_SEARCH":
        raise DomainError("Planner intent is not supported.", 422)
    control = svc.control(query.control_id)
    svc.access(query.scope_id)
    allowed = descendants(control.scope_id, svc.scopes)
    if query.scope_id not in allowed:
        raise DomainError("Selected scope is outside this control.", 422)
    impl = svc.implementation(svc.revision(control))
    if impl.template_id != "azure-search-public-access-v1":
        raise DomainError("The interactive demo currently supports the Azure Search template only.", 422)
    obj = svc.db.scalar(select(m.Assessment).where(m.Assessment.control_id == control.id,
        m.Assessment.scope_id == query.scope_id).order_by(m.Assessment.ordinal.desc()))
    # A newly selected scope uses the existing authorized, read-only-cloud assessment service.
    a = svc.assessment_view(obj) if obj else svc.run_assessment(control.id, query.scope_id)
    report = a["report"]
    if len(report["rows"]) > 100:
        raise DomainError("Select a smaller scope; this bounded demo renders at most 100 resources.", 422)
    current_control = svc.control_view(control)
    # Historical assessment findings are explicitly marked stale; current policy intent remains authoritative.
    resources = report["rows"]
    applicable_ids = {r["id"] for r in resources if r["result"] != "NOT_APPLICABLE"}
    snap = svc.get(m.InventorySnapshot, a["snapshot_id"])
    permissions = PERMISSIONS.get(svc.user.role, set())
    nodes = [dict(id="root", component="EngineeringWorkspace", children=CHILDREN)]

    def add(key, component, data):
        nodes.append(dict(id=key, component=component, data=data))

    add("summary", "ControlSummary", dict(control_id=control.id, name=current_control["name"],
        objective=current_control["objective"], revision=control.latest_revision,
        severity=current_control["severity"], scope_name=svc.scopes[query.scope_id]["name"]))
    add("impact", "ImpactAssessment", dict(assessment_id=a["id"], scope_id=a["scope_id"],
        scopes=[dict(id=sid, label=svc.scopes[sid]["name"]) for sid in sorted(allowed)
                if in_scope(sid, svc.user.grants, svc.scopes)], evaluated=report["evaluated"],
        counts=report["counts"], rows=[{k: r.get(k) for k in Resource.model_fields} for r in resources],
        predicted_denied=report["predicted_denied"], requests_total=len(report["requests"]),
        applications=sorted({r["application"] for r in resources if r["result"] in {"NON_COMPLIANT", "UNKNOWN"}})))
    add("policy", "PolicyDiffViewer", dict(baseline=[dict(id=b["id"], scope_id=b["scope_id"],
        effect=b["content"].get("effect", "Unknown"), observed_at=b["observed_at"])
        for b in a["context"]["baseline"]], proposed_document=json.dumps(impl.document, indent=2),
        implementation_digest=impl.document_digest, limitation=report["limitation"]))
    add("evidence", "EvidencePanel", dict(snapshot_id=snap.id, assessed_at=a["created_at"],
        collected_at=aware(snap.collected_at).isoformat(), blockers=report["blockers"], items=[
            dict(label="Observed configuration", kind="OBSERVED", detail="Persisted synthetic inventory and native-exemption records; no live cloud scan."),
            dict(label="Request impact", kind="SIMULATION_ESTIMATE", detail="Predictions apply only to the recorded sample requests. Resource counts are not outage predictions."),
            dict(label="Connectivity readiness", kind="OBSERVED", detail="READY is a synthetic fixture assertion. Private endpoints, DNS and application connectivity have not been tested."),
            dict(label="Recommended next step", kind="DETERMINISTIC_GUIDANCE", detail="Resolve blockers, obtain connectivity evidence and review expiring exceptions before preparing a pilot. No AI suggestions were generated.")]))
    add("exceptions", "ExceptionReview", dict(items=[{k: e[k] for k in ExceptionItem.model_fields}
        for e in svc.exceptions(control.id) if applicable_ids.intersection(e["resource_ids"])],
        request_options=[dict(id=r["id"], label=r["name"]) for r in resources
                         if r["result"] in {"NON_COMPLIANT", "UNKNOWN"}]))
    rollouts = svc.db.scalars(select(m.Rollout).join(m.Assessment, m.Rollout.assessment_id == m.Assessment.id)
                             .where(m.Assessment.control_id == control.id)).all()
    add("rollout", "RolloutTimeline", dict(ready=report["ready"] and a["current"],
        existing=[dict(id=r.id, stage=r.stage, delivery_state=r.delivery_state) for r in rollouts
                  if r.manifest["scope_id"] == query.scope_id], next_steps=[
            "Resolve configuration, ownership and connectivity evidence gaps.",
            "Review time-bound exceptions and confirm native exemption state.",
            "Prepare a version-bound package with a Cloud Engineering recovery runbook.",
            "Collect distinct Security and Cloud Engineering reviews, then stage a pilot."]))
    add("gate", "ApprovalGate", dict(current=a["current"], ready=report["ready"], stale_reasons=a["stale_reasons"],
        can_assess="assess" in permissions, can_request="request" in permissions, can_plan="plan" in permissions))
    sid = "control-" + uuid4().hex
    bundle = SurfaceBundle.model_validate(dict(mode="DETERMINISTIC", surface_id=sid, assessment_id=a["id"],
        expected_revision=control.latest_revision, evidence_digest=evidence_digest(a), messages=[
            dict(version=VERSION, createSurface=dict(surfaceId=sid, catalogId=CATALOG)),
            dict(version=VERSION, updateComponents=dict(surfaceId=sid, components=nodes))]))
    svc.audit("ASSISTANT_SURFACE_RENDERED", a["id"], query.scope_id,
              {"planner": "DETERMINISTIC", "question_digest": digest(query.question), "current": a["current"]})
    return bundle.model_dump(mode="json")


def check_evidence(svc, command, allow_stale=False):
    obj = svc.get(m.Assessment, command.assessment_id)
    svc.access(obj.scope_id)
    control = svc.control(obj.control_id)
    if command.expected_revision != control.latest_revision:
        raise DomainError("Control revision changed. Reopen the workspace.")
    a = svc.assessment_view(obj)
    if command.evidence_digest != evidence_digest(a):
        raise DomainError("Evidence reference does not match this assessment.")
    if not allow_stale and not a["current"]:
        raise DomainError("Evidence is stale. Refresh the assessment before continuing.")
    return obj, a


def execute(svc, command: Command):
    permission = {"refresh_assessment": "assess", "draft_exception": "request", "prepare_handoff": "plan"}[command.name]
    svc.permission(permission)
    obj, assessment = check_evidence(svc, command, allow_stale=command.name == "refresh_assessment")
    if command.name == "refresh_assessment":
        result = svc.run_assessment(obj.control_id, obj.scope_id)
        response = {"assessment_id": result["id"], "outcome": "ASSESSMENT_REFRESHED"}
    elif command.name == "prepare_handoff":
        # Navigation into a trusted, conventional human review form; no rollout is created here.
        response = {"assessment_id": obj.id, "outcome": "HUMAN_REVIEW_REQUIRED"}
    else:
        eligible = {r["id"] for r in assessment["report"]["rows"] if r["result"] in {"NON_COMPLIANT", "UNKNOWN"}}
        if not command.resource_ids or len(set(command.resource_ids)) != len(command.resource_ids) or not set(command.resource_ids) <= eligible:
            raise DomainError("Select applicable assessed resources that require an exception review.", 422)
        intent = m.AssistantIntent(actor_id=svc.user.id, assessment_id=obj.id,
            evidence_digest=command.evidence_digest, expected_revision=command.expected_revision,
            resource_ids=command.resource_ids, expires_at=svc.now+timedelta(minutes=10))
        svc.db.add(intent)
        svc.db.flush()
        response = {"intent_id": intent.id, "outcome": "HUMAN_REVIEW_REQUIRED", "resource_ids": intent.resource_ids,
                    "scope_id": obj.scope_id, "expires_at": aware(intent.expires_at).isoformat(),
                    "suggested_exception_expiry": (svc.now+timedelta(days=7)).isoformat()}
    svc.audit("ASSISTANT_COMMAND_COMPLETED", obj.id, obj.scope_id,
              {"command": command.name, "outcome": response["outcome"], "cloud_mutations": 0})
    return response


def confirm_exception(svc, intent_id, data: HumanConfirmation):
    svc.permission("request")
    intent = svc.get(m.AssistantIntent, intent_id)
    if intent.actor_id != svc.user.id:
        raise DomainError("Confirmation belongs to another identity.", 403)
    if intent.result_id or aware(intent.expires_at) <= svc.now:
        raise DomainError("Confirmation was used or expired. Prepare a new draft.")
    command = Command(name="draft_exception", assessment_id=intent.assessment_id,
        expected_revision=intent.expected_revision, evidence_digest=intent.evidence_digest,
        resource_ids=intent.resource_ids)
    obj, _ = check_evidence(svc, command)
    result = svc.create_exception(ExceptionInput(control_id=obj.control_id, scope_id=obj.scope_id,
        resource_ids=intent.resource_ids, **data.model_dump(exclude={"confirmed"})))
    intent.result_id = result["id"]
    svc.db.flush()  # Optimistic concurrency makes simultaneous confirmation consume only once.
    svc.audit("ASSISTANT_EXCEPTION_CONFIRMED", result["id"], obj.scope_id,
              {"intent_id": intent.id, "outcome": "REQUESTED", "cloud_mutations": 0})
    return result

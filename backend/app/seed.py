"""Deterministic synthetic fixture contents; relative timestamps make a fresh seed usable."""
from copy import deepcopy
from datetime import timedelta

from sqlalchemy import select, func

from . import models as m
from .domain import AWS_TEMPLATE, AZURE_TEMPLATE, digest, utcnow


def fixtures(ready=False):
    resources = []
    for idx, (name, value, owner, readiness) in enumerate([
        ("search-claims", "Disabled", "Claims", "READY"),
        ("search-customer", "Enabled", "Customer Experience", "BLOCKED"),
        ("search-assistant", "Enabled", "Digital Assistant", "BLOCKED"),
        ("search-analytics", "Enabled", "Analytics", "BLOCKED"),
        ("search-legacy", "Enabled", "Legacy Platform", "READY"),
        ("search-partner", "Enabled", "Partner Services", "BLOCKED"),
        ("search-unmapped", None, None, "UNKNOWN"),
    ]):
        resources.append({"id": f"search-{idx+1}", "name": name, "type": "Microsoft.Search/searchServices",
                          "scope_id": "az-prod", "provider": "AZURE", "application": owner or "Unmapped",
                          "owner": owner, "readiness": readiness,
                          "configuration": {"publicNetworkAccess": value} if value else {},
                          "readiness_evidence": "Synthetic readiness fixture; no connectivity test executed."})
    resources.append({"id": "storage-1", "name": "storage-documents", "type": "Microsoft.Storage/storageAccounts",
                      "scope_id": "az-prod", "provider": "AZURE", "application": "Documents", "owner": "Documents",
                      "readiness": "READY", "configuration": {}})
    resources.append({"id": "search-dev", "name": "search-sandbox", "type": "Microsoft.Search/searchServices",
                      "scope_id": "az-dev", "provider": "AZURE", "application": "Sandbox", "owner": "Sandbox",
                      "readiness": "BLOCKED", "configuration": {"publicNetworkAccess": "Enabled"}})
    for idx, bits in enumerate([True, False, None]):
        resources.append({"id": f"bucket-{idx+1}", "name": ["claims-archive", "analytics-export", "unmapped-bucket"][idx],
                          "type": "AWS::S3::Bucket", "provider": "AWS", "scope_id": ["aws-account-a", "aws-account-b", "aws-account-b"][idx],
                          "application": "Data Platform", "owner": "Data Platform", "readiness": "READY" if bits else "BLOCKED",
                          "configuration": {"accountBlockPublicAccess": {k: bits for k in
                              ["BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets"]}}})
    if ready:
        for r in resources:
            if r["scope_id"] == "az-prod" and r["type"] == "Microsoft.Search/searchServices":
                r["configuration"] = {"publicNetworkAccess": "Enabled" if r["id"] == "search-5" else "Disabled"}
                r["owner"] = r["owner"] or "Demo owner resolved"
                r["readiness"] = "READY"
    requests = [{"id": "request-1", "scope_id": "az-prod", "action": "create", "publicNetworkAccess": "Enabled"},
                {"id": "request-2", "scope_id": "az-prod", "action": "update", "publicNetworkAccess": "Disabled"},
                {"id": "request-3", "scope_id": "aws-account-a", "action": "s3:PutAccountPublicAccessBlock",
                 "principal_kind": "member_role"},
                {"id": "request-4", "scope_id": "aws-account-a", "action": "s3:PutAccountPublicAccessBlock",
                 "principal_kind": "service_linked_role"}]
    return resources, requests


def add_snapshot(db, ready=False, now=None):
    resources, requests = fixtures(ready)
    obj = m.InventorySnapshot(label="Remediated demo fixture" if ready else "Initial risk fixture",
                              ordinal=(db.scalar(select(func.max(m.InventorySnapshot.ordinal))) or 0) + 1,
                              resources=resources, requests=requests,
                              content_digest=digest({"resources": resources, "requests": requests}),
                              collected_at=now or utcnow())
    db.add(obj)
    db.flush()
    return obj


def seed(db, now=None):
    if db.scalar(select(m.User.id).limit(1)):
        return False
    now = now or utcnow()
    scopes = [
        ("az-root", "Azure estate", "AZURE", "MANAGEMENT_GROUP", None, "/providers/Microsoft.Management/managementGroups/demo"),
        ("az-prod", "Azure · Production", "AZURE", "SUBSCRIPTION", "az-root", "/subscriptions/00000000-0000-4000-8000-000000000001"),
        ("az-dev", "Azure · Development", "AZURE", "SUBSCRIPTION", "az-root", "/subscriptions/00000000-0000-4000-8000-000000000002"),
        ("aws-root", "AWS estate", "AWS", "ROOT", None, "r-demo"),
        ("aws-prod", "AWS · Production OU", "AWS", "OU", "aws-root", "ou-demo-prod00001"),
        ("aws-account-a", "AWS · Claims account", "AWS", "ACCOUNT", "aws-prod", "111111111111"),
        ("aws-account-b", "AWS · Analytics account", "AWS", "ACCOUNT", "aws-prod", "222222222222"),
    ]
    for sid, name, provider, kind, parent, native in scopes:
        db.add(m.Scope(id=sid, name=name, provider=provider, kind=kind, parent_id=parent, native_id=native))
        db.flush()
    for sid, name, role in [("engineer", "Jordan · Control engineer", "CONTROL_ENGINEER"),
        ("security", "Morgan · Security approver", "SECURITY_APPROVER"),
        ("cloud", "Alex · Cloud engineer", "CLOUD_ENGINEER"),
        ("requester", "Sam · Application owner", "EXCEPTION_REQUESTER"),
        ("viewer", "Taylor · Viewer", "VIEWER"), ("admin", "Casey · Demo administrator", "ADMIN"),
        ("dev-requester", "Dev-only application owner", "EXCEPTION_REQUESTER")]:
        db.add(m.User(id=sid, name=name, role=role, grants=["az-dev"] if sid == "dev-requester" else ["az-root", "aws-root"]))
    db.flush()
    for cid, scope, template, document, name, objective in [
        ("azure-search", "az-prod", "azure-search-public-access-v1", AZURE_TEMPLATE,
         "Prevent public access to Azure AI Search", "Enterprise search services must disable public network access unless an effective, time-bound exemption applies."),
        ("aws-s3", "aws-prod", "aws-s3-account-bpa-v1", AWS_TEMPLATE,
         "Protect S3 public-access safeguards", "Require a verified account Block Public Access baseline before restricting changes to that baseline.")]:
        db.add(m.Control(id=cid, scope_id=scope, latest_revision=1, lifecycle="DRAFT", created_at=now))
        db.flush()
        db.add(m.ControlRevision(id=cid + "-v1", control_id=cid, revision=1, author_id="engineer", created_at=now,
            content={"name": name, "objective": objective, "rationale": "Recurring public-access configuration risks need a governed preventive control.",
                     "severity": "HIGH", "security_owner": "Cloud Security", "engineering_owner": "Cloud Engineering",
                     "evidence": "Synthetic posture findings; no Wiz connection or enterprise resource data.",
                     "change_reason": "Initial demo control"}))
        db.flush()
        db.add(m.Implementation(id=cid + "-implementation-v1", revision_id=cid + "-v1", template_id=template,
                                document=deepcopy(document), document_digest=digest(document)))
    db.add(m.PolicyBinding(id="azure-existing-audit", scope_id="az-prod", provider="AZURE", native_id="mock:azure/search-audit",
        content={"owner": "Cloud Engineering", "effect": "Audit", "coverage": "existing audit-only baseline", "provenance": "DEMO"}, observed_at=now))
    db.add(m.PolicyBinding(id="aws-existing-deny", scope_id="aws-account-a", provider="AWS", native_id="mock:aws/account-a-bpa-scp",
        content={"owner": "Cloud Engineering", "effect": "Deny", "action": "s3:PutAccountPublicAccessBlock",
                 "coverage": "existing single-account restriction; other account lacks baseline", "provenance": "DEMO"}, observed_at=now))
    for eid, resource, status, native, days in [
        ("exception-pending", "search-3", "REQUESTED", "NOT_REQUESTED", 20),
        ("exception-unapplied", "search-4", "APPROVED", "PENDING", 6),
        ("exception-effective", "search-5", "APPROVED", "APPLIED", 25),
        ("exception-expired", "search-6", "APPROVED", "APPLIED", -1),
    ]:
        db.add(m.ExceptionRequest(id=eid, control_id="azure-search", scope_id="az-prod", requester_id="requester",
                                  approver_id="security" if status == "APPROVED" else None,
                                  resource_ids=[resource], justification="Temporary legacy dependency awaiting application migration.",
                                  compensating_controls="Restricted client networks and application authentication (synthetic evidence).",
                                  risk_owner="Demo application risk owner", expires_at=now+timedelta(days=days), status=status,
                                  native_status=native, representation="AZURE_EXEMPTION",
                                  native_reference=f"mock:azure/assignment/search/exemptions/{eid}" if native == "APPLIED" else None,
                                  created_at=now))
    db.add(m.ExceptionRequest(id="exception-unsupported", control_id="aws-s3", scope_id="aws-account-b",
                              requester_id="requester", resource_ids=["bucket-2"], justification="Requested bucket-only public website exception.",
                              compensating_controls="Application authentication and logs proposed.", risk_owner="Demo data owner",
                              expires_at=now+timedelta(days=10), status="REQUESTED", native_status="NOT_REQUESTED",
                              representation="UNSUPPORTED", created_at=now))
    add_snapshot(db, now=now)
    db.add(m.AuditEvent(actor_id="system", scope_id="az-root", action="DEMO_SEEDED", object_id="seed-v1",
                       detail={"synthetic": True, "cloud_mutations": 0}, correlation_id="seed", created_at=now))
    db.flush()
    # Initial assessments are explicit synthetic evidence, not cloud scans.
    from .config import Settings
    from .services import Service
    svc = Service(db, db.get(m.User, "engineer"), now, Settings(app_env="local"), "seed-assessment")
    svc.run_assessment("azure-search", "az-prod")
    svc.run_assessment("aws-s3", "aws-prod")
    return True

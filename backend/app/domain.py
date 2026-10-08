"""Pure deterministic rules. No ORM, network clients, or infrastructure writes."""
import hashlib
import json
from datetime import datetime, timedelta, timezone


class DomainError(Exception):
    def __init__(self, message, status=409):
        self.message, self.status = message, status


def utcnow():
    return datetime.now(timezone.utc)


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def digest(value):
    try:
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    except (TypeError, ValueError):
        raise DomainError("Only finite, JSON-compatible values are supported.", 422)


def fresh(timestamp, now, hours=24):
    age = aware(now) - aware(timestamp)
    return timedelta(0) <= age <= timedelta(hours=hours)


PERMISSIONS = {
    "VIEWER": {"read"},
    "CONTROL_ENGINEER": {"read", "author", "assess", "plan", "export", "request"},
    "EXCEPTION_REQUESTER": {"read", "request"},
    "SECURITY_APPROVER": {"read", "security_approve", "exception_approve", "export"},
    "CLOUD_ENGINEER": {"read", "engineering_approve", "export", "receipt", "plan"},
    "ADMIN": {"read", "admin"},
}


def authorize(role, permission):
    if permission not in PERMISSIONS.get(role, set()):
        raise DomainError("This identity does not have the required permission.", 403)


def descendants(scope_id, scopes):
    if scope_id not in scopes:
        raise DomainError("Unknown target scope.", 422)
    result, pending = set(), [scope_id]
    while pending:
        current = pending.pop()
        if current in result:
            continue
        result.add(current)
        pending.extend(s["id"] for s in scopes.values() if s.get("parent_id") == current)
    return result


def in_scope(scope_id, grants, scopes):
    return any(scope_id in descendants(grant, scopes) for grant in grants if grant in scopes)


def exception_disposition(exc, now):
    if exc["status"] == "REVOKED":
        return "REVOKED"
    if exc["status"] == "REJECTED":
        return "REJECTED"
    expiry = datetime.fromisoformat(exc["expires_at"])
    if aware(expiry) <= aware(now):
        return "EXPIRED"
    if exc.get("representation") == "UNSUPPORTED":
        return "UNSUPPORTED"
    if exc["status"] != "APPROVED":
        return "PENDING"
    if exc.get("native_status") == "APPLIED":
        return "EFFECTIVE"
    return "APPROVED_UNAPPLIED"


AZURE_ID = "/providers/Microsoft.Authorization/policyDefinitions/ee980b6d-0eca-4501-8d54-f6290fd512c3"
AZURE_TEMPLATE = {"policyDefinitionId": AZURE_ID, "definitionVersion": "1.0.1",
                  "parameters": {"effect": {"value": "Deny"}}, "enforcementMode": "Default"}
AWS_TEMPLATE = {"Version": "2012-10-17", "Statement": [{"Sid": "ProtectAccountPublicAccessBlock",
                "Effect": "Deny", "Action": "s3:PutAccountPublicAccessBlock", "Resource": "*"}]}


class PolicyProvider:
    provider = ""
    template_id = ""
    document = {}
    scopes = ()
    resource_type = ""
    limitation = ""

    def capabilities(self):
        return {"provider": self.provider, "template_id": self.template_id, "scope_types": self.scopes,
                "live_deployment": False, "evaluator": "fixture-v1", "limitation": self.limitation}

    def validate_implementation(self, document):
        if digest(document) != digest(self.document):
            raise DomainError("UNSUPPORTED: only the exact documented fixture template is evaluable.", 422)
        return {"status": "VALID", "method": "exact supported-template digest", "live_verified": False}

    def generate_change_artifacts(self, document, native_scope):
        self.validate_implementation(document)
        return {"provider": self.provider, "scope": native_scope, "document": document,
                "artifact_kind": "REVIEW_ONLY", "provenance": "DEMO", "execute": False}


class AzurePolicyProvider(PolicyProvider):
    provider = "AZURE"
    template_id = "azure-search-public-access-v1"
    document = AZURE_TEMPLATE
    scopes = ("MANAGEMENT_GROUP", "SUBSCRIPTION", "RESOURCE_GROUP")
    resource_type = "Microsoft.Search/searchServices"
    limitation = "Create/update guardrail only; no existing-resource remediation or connectivity proof."

    def configuration(self, resource):
        value = resource.get("configuration", {}).get("publicNetworkAccess")
        if value not in {"Enabled", "Disabled"}:
            return "UNKNOWN", "publicNetworkAccess missing or unsupported; no default inferred."
        return ("COMPLIANT", "Public access explicitly disabled.") if value == "Disabled" else (
            "NON_COMPLIANT", "Public access enabled; this does not establish unauthenticated exposure.")

    def request(self, req):
        if req.get("action") not in {"create", "update"}:
            return "UNKNOWN"
        val = req.get("publicNetworkAccess")
        return "PREDICTED_DENIED" if val == "Enabled" else (
            "NOT_DENIED_BY_CONTROL" if val == "Disabled" else "UNKNOWN")


class AwsScpProvider(PolicyProvider):
    provider = "AWS"
    template_id = "aws-s3-account-bpa-v1"
    document = AWS_TEMPLATE
    scopes = ("ROOT", "OU", "ACCOUNT")
    resource_type = "AWS::S3::Bucket"
    limitation = "Requires all four account BPA safeguards first; no native audit effect; SCP coverage exclusions apply."

    def configuration(self, resource):
        bits = resource.get("configuration", {}).get("accountBlockPublicAccess")
        names = {"BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets"}
        if not isinstance(bits, dict) or not names.issubset(bits) or any(type(bits[k]) is not bool for k in names):
            return "UNKNOWN", "Account Block Public Access prerequisite is not known."
        if not all(bits[k] for k in names):
            return "NON_COMPLIANT", "Account baseline insecure; an SCP cannot establish Block Public Access."
        return "COMPLIANT", "All four account safeguards observed in fixture; SCP protects subsequent changes."

    def request(self, req):
        if req.get("principal_kind") not in {"member_role", "member_user", "member_root"}:
            return "UNKNOWN"
        if req.get("action") == "s3:PutAccountPublicAccessBlock":
            return "PREDICTED_DENIED"
        return "UNKNOWN"


PROVIDERS = {p.template_id: p for p in [AzurePolicyProvider(), AwsScpProvider()]}


def provider_for(template_id):
    if template_id not in PROVIDERS:
        raise DomainError("UNSUPPORTED implementation template.", 422)
    return PROVIDERS[template_id]


def assess(provider, document, resources, exceptions, requests, scope_ids, now):
    provider.validate_implementation(document)
    rows, blockers = [], []
    counts = {key: 0 for key in ("COMPLIANT", "NON_COMPLIANT", "UNKNOWN", "NOT_APPLICABLE")}
    for resource in resources:
        if resource["scope_id"] not in scope_ids:
            continue
        applicable = resource["type"].lower() == provider.resource_type.lower()
        result, reason = provider.configuration(resource) if applicable else ("NOT_APPLICABLE", "Different resource type.")
        matches = [e for e in exceptions if resource["id"] in e["resource_ids"]]
        dispositions = [exception_disposition(e, now) for e in matches]
        order = ("EFFECTIVE", "APPROVED_UNAPPLIED", "PENDING", "UNSUPPORTED", "EXPIRED", "REVOKED", "REJECTED")
        disposition = next((d for d in order if d in dispositions), "NONE")
        ready = "NOT_APPLICABLE" if not applicable else (
            "READY" if resource.get("owner") and resource.get("readiness") == "READY" else "BLOCKED")
        if applicable:
            if result == "UNKNOWN":
                blockers.append(f"{resource['name']}: configuration evidence unknown")
            if not resource.get("owner"):
                blockers.append(f"{resource['name']}: application owner missing")
            if result == "NON_COMPLIANT" and disposition != "EFFECTIVE":
                blockers.append(f"{resource['name']}: remediate or apply a reviewed native exemption")
            if ready != "READY" and disposition != "EFFECTIVE":
                blockers.append(f"{resource['name']}: readiness evidence missing")
            if provider.provider == "AWS" and result != "COMPLIANT":
                blockers.append(f"{resource['name']}: account BPA prerequisite must be established")
        counts[result] += 1
        rows.append({**resource, "result": result, "reason": reason, "exception": disposition, "readiness_result": ready})
    request_results = [{**r, "result": provider.request(r)} for r in requests if r.get("scope_id") in scope_ids]
    if not any(r["result"] != "NOT_APPLICABLE" for r in rows):
        blockers.append("No applicable resources in target; cannot assert coverage.")
    return {"rows": rows, "counts": counts, "evaluated": len(rows), "requests": request_results,
            "predicted_denied": sum(r["result"] == "PREDICTED_DENIED" for r in request_results) if request_results else None,
            "applications": sorted({r["application"] for r in rows if r.get("application") and r["result"] != "NOT_APPLICABLE"}),
            "blockers": sorted(set(blockers)), "ready": not blockers, "confidence": "FIXTURE_ONLY",
            "limitation": provider.limitation, "provenance": "DEMO"}

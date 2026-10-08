"""Transactional application services; cloud changes leave only as review artifacts."""
from datetime import datetime, timedelta

from sqlalchemy import select, func

from . import models as m
from .domain import (DomainError, assess, authorize, aware, descendants, digest,
                     exception_disposition, fresh, in_scope, provider_for)


def record(obj):
    return {col.name: (getattr(obj, col.name).isoformat() if hasattr(getattr(obj, col.name), "isoformat")
                       else getattr(obj, col.name)) for col in obj.__table__.columns}


class Service:
    def __init__(self, db, user, now, settings, correlation="local"):
        self.db, self.user, self.now, self.settings, self.correlation = db, user, now, settings, correlation
        self.scopes = {s.id: record(s) for s in db.scalars(select(m.Scope)).all()}

    def permission(self, action):
        authorize(self.user.role, action)

    def access(self, scope_id):
        if not in_scope(scope_id, self.user.grants, self.scopes):
            raise DomainError("Scope is outside this identity's grants.", 403)

    def audit(self, action, obj_id, scope_id, detail=None):
        self.db.add(m.AuditEvent(actor_id=self.user.id, action=action, object_id=obj_id, scope_id=scope_id,
                                detail=detail or {}, correlation_id=self.correlation, created_at=self.now))

    def get(self, model, key):
        result = self.db.get(model, key)
        if result is None:
            raise DomainError("Object not found.", 404)
        return result

    def control(self, key):
        obj = self.get(m.Control, key)
        self.access(obj.scope_id)
        return obj

    def revision(self, control):
        return self.db.scalar(select(m.ControlRevision).where(m.ControlRevision.control_id == control.id,
                              m.ControlRevision.revision == control.latest_revision))

    def implementation(self, revision):
        return self.db.scalar(select(m.Implementation).where(m.Implementation.revision_id == revision.id))

    def snapshot(self):
        snap = self.db.scalar(select(m.InventorySnapshot).order_by(m.InventorySnapshot.ordinal.desc()))
        if snap is None:
            raise DomainError("No inventory snapshot. Run the seed command.")
        return snap

    def exceptions(self, control_id=None):
        query = select(m.ExceptionRequest).order_by(m.ExceptionRequest.created_at.desc())
        if control_id:
            query = query.where(m.ExceptionRequest.control_id == control_id)
        return [self.exception_view(e) for e in self.db.scalars(query).all()
                if in_scope(e.scope_id, self.user.grants, self.scopes)]

    def exception_view(self, obj):
        data = record(obj)
        data["disposition"] = exception_disposition(data, self.now)
        data["cleanup_required"] = data["disposition"] in {"EXPIRED", "REVOKED"} and obj.native_status in {"APPLIED", "REMOVAL_PENDING"}
        return data

    def context(self, control, scope_id):
        scopes = descendants(scope_id, self.scopes)
        bindings = [record(b) for b in self.db.scalars(select(m.PolicyBinding)).all()
                    if scopes.intersection(descendants(b.scope_id, self.scopes))]
        exceptions = sorted(self.exceptions(control.id), key=lambda e: e["id"])
        return {"scope_ids": sorted(scopes), "baseline": sorted(bindings, key=lambda b: b["id"]),
                "exceptions": exceptions, "exception_digest": digest(exceptions),
                "baseline_digest": digest(sorted(bindings, key=lambda b: b["id"]))}

    def control_view(self, obj):
        rev = self.revision(obj)
        impl = self.implementation(rev)
        result = {**record(obj), **rev.content, "revision_id": rev.id, "author_id": rev.author_id,
                  "implementation": record(impl), "provider": provider_for(impl.template_id).provider}
        last = self.db.scalar(select(m.Assessment).where(m.Assessment.control_id == obj.id)
                              .order_by(m.Assessment.ordinal.desc()))
        result["latest_assessment"] = self.assessment_view(last) if last else None
        return result

    def controls(self):
        return [self.control_view(c) for c in self.db.scalars(select(m.Control).order_by(m.Control.created_at)).all()
                if in_scope(c.scope_id, self.user.grants, self.scopes)]

    def create_control(self, data):
        self.permission("author")
        self.access(data.scope_id)
        provider = provider_for(data.template_id)
        if self.scopes[data.scope_id]["provider"] != provider.provider:
            raise DomainError("Provider does not match the control's owning scope.", 422)
        doc = data.document if data.document is not None else provider.document
        provider.validate_implementation(doc)
        control = m.Control(scope_id=data.scope_id)
        self.db.add(control)
        self.db.flush()
        self.add_revision(control, data, doc)
        self.audit("CONTROL_CREATED", control.id, control.scope_id)
        self.db.flush()
        return self.control_view(control)

    def add_revision(self, control, data, doc):
        content = data.model_dump(exclude={"scope_id", "template_id", "document", "expected_revision"})
        rev = m.ControlRevision(control_id=control.id, revision=control.latest_revision,
                                author_id=self.user.id, content=content, created_at=self.now)
        self.db.add(rev)
        self.db.flush()
        self.db.add(m.Implementation(revision_id=rev.id, template_id=data.template_id,
                                     document=doc, document_digest=digest(doc)))
        self.db.flush()

    def revise(self, control_id, data):
        self.permission("author")
        control = self.control(control_id)
        if data.expected_revision != control.latest_revision:
            raise DomainError("Revision changed; reload before editing.")
        if data.scope_id != control.scope_id:
            raise DomainError("Changing owning scope requires a separate control in this MVP.", 422)
        if control.lifecycle == "RETIRED":
            raise DomainError("Retired controls cannot be revised.")
        provider = provider_for(data.template_id)
        if provider.provider != self.scopes[control.scope_id]["provider"]:
            raise DomainError("Provider does not match owning scope.", 422)
        doc = data.document if data.document is not None else provider.document
        provider.validate_implementation(doc)
        control.latest_revision += 1
        control.lifecycle = "DRAFT"
        self.add_revision(control, data, doc)
        self.audit("CONTROL_REVISED", control.id, control.scope_id,
                   {"revision": control.latest_revision, "reason": data.change_reason})
        return self.control_view(control)

    def retire(self, control_id):
        self.permission("author")
        control = self.control(control_id)
        control.lifecycle = "RETIRED"
        self.audit("CONTROL_RETIRED", control.id, control.scope_id,
                   {"note": "Catalog retirement does not remove native enforcement."})
        return {"status": "RETIRED"}

    def delete_draft(self, control_id):
        self.permission("author")
        control = self.control(control_id)
        if control.lifecycle != "DRAFT" or control.latest_revision != 1:
            raise DomainError("Only unreferenced initial drafts may be deleted; retire this control.")
        if self.db.scalar(select(m.Assessment).where(m.Assessment.control_id == control_id)) or self.exceptions(control_id):
            raise DomainError("Referenced controls must be retained.")
        rev = self.revision(control)
        self.db.delete(self.implementation(rev))
        self.db.flush()
        self.db.delete(rev)
        self.db.flush()
        self.audit("DRAFT_DELETED", control_id, control.scope_id)
        self.db.delete(control)

    def run_assessment(self, control_id, scope_id):
        self.permission("assess")
        control = self.control(control_id)
        self.access(scope_id)
        if scope_id not in descendants(control.scope_id, self.scopes):
            raise DomainError("Assessment cannot expand beyond the control's owning scope.", 422)
        rev, snap = self.revision(control), self.snapshot()
        impl = self.implementation(rev)
        provider = provider_for(impl.template_id)
        if self.scopes[scope_id]["kind"] not in provider.scopes:
            raise DomainError("Unsupported target scope type.", 422)
        context = self.context(control, scope_id)
        report = assess(provider, impl.document, snap.resources, context["exceptions"], snap.requests,
                        set(context["scope_ids"]), self.now)
        if not fresh(snap.collected_at, self.now, self.settings.evidence_hours):
            report["blockers"].append("Inventory evidence is stale.")
        if any(not fresh(datetime.fromisoformat(b["observed_at"]), self.now,
                         self.settings.evidence_hours) for b in context["baseline"]):
            report["blockers"].append("Baseline policy evidence is stale.")
        report["ready"] = not report["blockers"]
        obj = m.Assessment(control_id=control.id, revision_id=rev.id, implementation_id=impl.id,
                           ordinal=(self.db.scalar(select(func.max(m.Assessment.ordinal))) or 0) + 1,
                           snapshot_id=snap.id, scope_id=scope_id, author_id=self.user.id,
                           context=context, report=report, created_at=self.now)
        self.db.add(obj)
        self.db.flush()
        self.audit("ASSESSMENT_COMPLETED", obj.id, scope_id, {"counts": report["counts"], "demo": True})
        return self.assessment_view(obj)

    def assessment_view(self, obj):
        data = record(obj)
        data["stale_reasons"] = self.stale_reasons(obj)
        data["current"] = not data["stale_reasons"]
        return data

    def stale_reasons(self, assessment):
        control = self.get(m.Control, assessment.control_id)
        context = self.context(control, assessment.scope_id)
        reasons = []
        if control.lifecycle == "RETIRED":
            reasons.append("Control retired")
        if self.revision(control).id != assessment.revision_id:
            reasons.append("Control revision changed")
        if self.snapshot().id != assessment.snapshot_id:
            reasons.append("A newer inventory snapshot exists")
        if not fresh(assessment.created_at, self.now, self.settings.evidence_hours):
            reasons.append("Assessment evidence expired")
        snap = self.get(m.InventorySnapshot, assessment.snapshot_id)
        if not fresh(snap.collected_at, self.now, self.settings.evidence_hours):
            reasons.append("Inventory evidence expired")
        for key in ("exception_digest", "baseline_digest", "scope_ids"):
            if context[key] != assessment.context[key]:
                reasons.append(f"{key.replace('_', ' ')} changed")
        return reasons

    def create_exception(self, data):
        self.permission("request")
        control = self.control(data.control_id)
        self.access(data.scope_id)
        if data.scope_id not in descendants(control.scope_id, self.scopes):
            raise DomainError("Exception scope is outside the control.", 422)
        if not self.now + timedelta(hours=1) < data.expires_at <= self.now + timedelta(days=90):
            raise DomainError("Expiry must be between one hour and 90 days from now.", 422)
        resources = {r["id"]: r for r in self.snapshot().resources}
        scope_ids = descendants(data.scope_id, self.scopes)
        provider = provider_for(self.implementation(self.revision(control)).template_id)
        for rid in data.resource_ids:
            r = resources.get(rid)
            if not r or r["scope_id"] not in scope_ids or r["type"].lower() != provider.resource_type.lower():
                raise DomainError("Resource is unknown, not applicable, or outside exception scope.", 422)
        if data.renewal_of:
            old = self.get(m.ExceptionRequest, data.renewal_of)
            if old.control_id != control.id or old.scope_id != data.scope_id:
                raise DomainError("Renewal must reference the same control and scope.", 422)
        obj = m.ExceptionRequest(**data.model_dump(), requester_id=self.user.id,
                                 representation="AZURE_EXEMPTION" if provider.provider == "AZURE" else "UNSUPPORTED",
                                 status="REQUESTED", native_status="NOT_REQUESTED", created_at=self.now)
        self.db.add(obj)
        self.db.flush()
        self.audit("EXCEPTION_REQUESTED", obj.id, obj.scope_id, {"expires_at": obj.expires_at.isoformat()})
        return self.exception_view(obj)

    def decide_exception(self, key, data):
        self.permission("exception_approve")
        obj = self.get(m.ExceptionRequest, key)
        self.access(obj.scope_id)
        if obj.version != data.expected_version:
            raise DomainError("Exception changed; reload.")
        if obj.requester_id == self.user.id:
            raise DomainError("Requesters cannot approve or review their own exceptions.", 403)
        transitions = {("REQUESTED", "REVIEW"): "SECURITY_REVIEW", ("SECURITY_REVIEW", "APPROVE"): "APPROVED",
                       ("REQUESTED", "REJECT"): "REJECTED", ("SECURITY_REVIEW", "REJECT"): "REJECTED",
                       ("APPROVED", "REVOKE"): "REVOKED"}
        target = transitions.get((obj.status, data.decision))
        if not target:
            raise DomainError("Invalid exception transition.")
        if target == "APPROVED" and (aware(obj.expires_at) <= self.now or obj.representation == "UNSUPPORTED"):
            raise DomainError("Expired or unrepresentable exceptions cannot be approved.")
        obj.status = target
        obj.approver_id = self.user.id
        if target == "APPROVED":
            obj.native_status = "PENDING"
        if target == "REVOKED" and obj.native_status == "APPLIED":
            obj.native_status = "REMOVAL_PENDING"
        self.audit("EXCEPTION_" + target, obj.id, obj.scope_id, {"reason": data.reason, "version": obj.version})
        self.db.flush()
        return self.exception_view(obj)

    def native_exception(self, key, data):
        self.permission("receipt")
        obj = self.get(m.ExceptionRequest, key)
        self.access(obj.scope_id)
        if obj.version != data.expected_version:
            raise DomainError("Exception changed; reload.")
        if data.status == "APPLIED" and (obj.status != "APPROVED" or aware(obj.expires_at) <= self.now
                                         or obj.representation == "UNSUPPORTED"):
            raise DomainError("Only valid approved representable exceptions can have a mock applied receipt.")
        if not data.reference.startswith("mock:"):
            raise DomainError("Only explicitly mock native references are accepted.", 422)
        obj.native_status = data.status
        obj.native_reference = data.reference
        self.audit("MOCK_EXCEPTION_OBSERVED", obj.id, obj.scope_id, {"status": data.status, "reference": data.reference})
        self.db.flush()
        return self.exception_view(obj)

    def create_rollout(self, data):
        self.permission("plan")
        assessment = self.get(m.Assessment, data.assessment_id)
        self.access(assessment.scope_id)
        control = self.control(assessment.control_id)
        impl = self.get(m.Implementation, assessment.implementation_id)
        manifest = {"schema_version": 1, "provenance": "DEMO", "live_deployment": False,
                    "control_id": control.id, "revision_id": assessment.revision_id,
                    "implementation_id": impl.id, "implementation_digest": impl.document_digest,
                    "document": impl.document, "scope_id": assessment.scope_id,
                    "scope_ids": assessment.context["scope_ids"], "assessment_id": assessment.id,
                    "assessment_digest": digest(assessment.report), "context": assessment.context,
                    "rollback": data.rollback, "reason": data.reason,
                    "rings": ["OBSERVATION", "PILOT", "LIMITED", "BROAD"],
                    "ring_note": "Rings do not expand target scope; a wider target requires a new assessment/package."}
        obj = m.Rollout(assessment_id=assessment.id, author_id=self.user.id, manifest=manifest,
                       manifest_digest=digest(manifest), created_at=self.now)
        self.db.add(obj)
        control.lifecycle = "IN_REVIEW"
        self.db.flush()
        self.audit("ROLLOUT_PLANNED", obj.id, assessment.scope_id, {"manifest_digest": obj.manifest_digest})
        return self.rollout_view(obj)

    def rollout(self, key):
        obj = self.get(m.Rollout, key)
        self.access(obj.manifest["scope_id"])
        return obj

    def approvals(self, obj):
        return self.db.scalars(select(m.Approval).where(m.Approval.rollout_id == obj.id)).all()

    def rollout_blockers(self, obj):
        assessment = self.get(m.Assessment, obj.assessment_id)
        blockers = list(assessment.report["blockers"]) + self.stale_reasons(assessment)
        if digest(obj.manifest) != obj.manifest_digest:
            blockers.append("Manifest digest mismatch")
        if obj.stage == "CANCELLED":
            blockers.append("Rollout cancelled")
        if any(a.decision == "REJECTED" for a in self.approvals(obj)):
            blockers.append("Reviewer rejected this package; create a new plan")
        return blockers

    def require_ready(self, obj, approvals=False):
        blockers = self.rollout_blockers(obj)
        if blockers:
            raise DomainError("Readiness blocked: " + "; ".join(blockers))
        if approvals:
            votes = [a for a in self.approvals(obj) if a.decision == "APPROVED" and a.manifest_digest == obj.manifest_digest]
            if {a.kind for a in votes} != {"SECURITY", "ENGINEERING"} or len({a.actor_id for a in votes}) < 2:
                raise DomainError("Distinct security and Cloud Engineering approvals are required.")

    def rollout_view(self, obj):
        return {**record(obj), "approvals": [record(a) for a in self.approvals(obj)],
                "blockers": self.rollout_blockers(obj),
                "observation_fresh": bool(obj.last_observed_at and fresh(obj.last_observed_at, self.now,
                                                                         self.settings.evidence_hours))}

    def approve(self, key, data):
        obj = self.rollout(key)
        kind = {"SECURITY_APPROVER": "SECURITY", "CLOUD_ENGINEER": "ENGINEERING"}.get(self.user.role)
        if not kind:
            raise DomainError("A delegated approver role is required.", 403)
        if obj.version != data.expected_version:
            raise DomainError("Rollout changed; reload before approving.")
        rev = self.get(m.ControlRevision, obj.manifest["revision_id"])
        if self.user.id in {obj.author_id, rev.author_id}:
            raise DomainError("Authors cannot approve their own change package.", 403)
        if self.db.scalar(select(m.Approval).where(m.Approval.rollout_id == key, m.Approval.actor_id == self.user.id)):
            raise DomainError("This identity already recorded a decision.")
        if data.decision == "APPROVED":
            self.require_ready(obj)
        self.db.add(m.Approval(rollout_id=key, actor_id=self.user.id, kind=kind, decision=data.decision,
                              reason=data.reason, manifest_digest=obj.manifest_digest, created_at=self.now))
        obj.version += 1
        self.db.flush()
        votes = self.approvals(obj)
        if {a.kind for a in votes if a.decision == "APPROVED"} == {"SECURITY", "ENGINEERING"}:
            self.control(obj.manifest["control_id"]).lifecycle = "APPROVED"
        self.audit("ROLLOUT_" + data.decision, key, obj.manifest["scope_id"],
                   {"kind": kind, "reason": data.reason, "manifest_digest": obj.manifest_digest})
        return self.rollout_view(obj)

    def transition(self, key, data):
        self.permission("plan")
        obj = self.rollout(key)
        if data.expected_version != obj.version:
            raise DomainError("Rollout changed; reload.")
        path = ["ASSESSMENT", "OBSERVATION", "PILOT", "LIMITED", "BROAD"]
        if data.stage in {"PAUSED", "CANCELLED"} and obj.stage != "CANCELLED":
            obj.stage = data.stage
        else:
            if obj.stage not in path or path.index(obj.stage) + 1 >= len(path) or data.stage != path[path.index(obj.stage) + 1]:
                raise DomainError("Invalid progression; paused plans require a new reviewed rollout.")
            self.require_ready(obj, approvals=data.stage != "OBSERVATION")
            if data.stage in {"LIMITED", "BROAD"} and (obj.delivery_state != "VERIFIED" or not obj.last_observed_at
                    or not fresh(obj.last_observed_at, self.now, self.settings.evidence_hours)):
                raise DomainError("A fresh matching mock observation is required before promotion.")
            obj.stage = data.stage
        self.audit("ROLLOUT_STAGE_CHANGED", key, obj.manifest["scope_id"], {"stage": obj.stage})
        self.db.flush()
        return self.rollout_view(obj)

    def export(self, key, draft=False):
        self.permission("export")
        obj = self.rollout(key)
        if not draft:
            self.require_ready(obj, approvals=True)
            if obj.stage not in {"PILOT", "LIMITED", "BROAD"}:
                raise DomainError("Approved exports require an active pilot or later ring.")
            obj.delivery_state = "EXPORTED"
        impl = self.get(m.Implementation, obj.manifest["implementation_id"])
        artifacts = provider_for(impl.template_id).generate_change_artifacts(
            impl.document, self.scopes[obj.manifest["scope_id"]]["native_id"])
        bundle = {"status": "DRAFT_UNAPPROVED" if draft else "APPROVED_DEMO_HANDOFF", "provenance": "DEMO",
                  "manifest": obj.manifest, "manifest_digest": obj.manifest_digest, "artifacts": artifacts,
                  "approvals": [record(a) for a in self.approvals(obj)],
                  "assessment": record(self.get(m.Assessment, obj.assessment_id)),
                  "pull_request_description": "Review-only demo: validate native behavior and environment readiness before any operational use.",
                  "receipt_contract": {"event_id": "unique-id", "manifest_digest": obj.manifest_digest,
                                       "scope_id": obj.manifest["scope_id"], "implementation_digest": impl.document_digest,
                                       "observed_at": "ISO8601 UTC", "status": "VERIFIED", "provenance": "DEMO"}}
        self.audit("DRAFT_EXPORTED" if draft else "APPROVED_HANDOFF_EXPORTED", key, obj.manifest["scope_id"],
                   {"manifest_digest": obj.manifest_digest})
        return bundle

    def receive(self, key, data):
        self.permission("receipt")
        obj = self.rollout(key)
        payload = data.model_dump(mode="json")
        existing = self.db.get(m.Receipt, data.event_id)
        if existing:
            if existing.rollout_id != key or existing.payload != payload:
                raise DomainError("Event ID reused with different content.")
            return record(existing)
        if obj.delivery_state == "NOT_EXPORTED" or obj.stage in {"PAUSED", "CANCELLED"}:
            raise DomainError("An active, approved export is required before receiving mock pipeline results.")
        if data.scope_id != obj.manifest["scope_id"] or data.manifest_digest != obj.manifest_digest:
            disposition = "MISMATCHED"
        elif aware(data.observed_at) > self.now + timedelta(seconds=5):
            disposition = "FUTURE_REJECTED"
        elif obj.last_observed_at and aware(data.observed_at) <= aware(obj.last_observed_at):
            disposition = "STALE"
        elif not fresh(data.observed_at, self.now, self.settings.evidence_hours):
            disposition = "STALE"
        else:
            self.require_ready(obj, approvals=True)
            disposition = data.status
            if data.implementation_digest != obj.manifest["implementation_digest"]:
                disposition = "DRIFTED"
            obj.delivery_state = disposition
            obj.last_observed_at = data.observed_at
        receipt = m.Receipt(id=data.event_id, rollout_id=key, payload=payload,
                            disposition=disposition, received_at=self.now)
        self.db.add(receipt)
        self.audit("MOCK_PIPELINE_RECEIPT", key, obj.manifest["scope_id"],
                   {"disposition": disposition, "event_id": data.event_id})
        self.db.flush()
        return record(receipt)

    def reconcile(self):
        self.permission("admin")
        changed = []
        for obj in self.db.scalars(select(m.ExceptionRequest)).all():
            if not in_scope(obj.scope_id, self.user.grants, self.scopes):
                continue
            if aware(obj.expires_at) <= self.now and obj.status not in {"EXPIRED", "REVOKED", "REJECTED"}:
                obj.status = "EXPIRED"
                if obj.native_status == "APPLIED":
                    obj.native_status = "REMOVAL_PENDING"
                self.audit("EXCEPTION_EXPIRED", obj.id, obj.scope_id, {"cloud_mutation": False})
                changed.append(obj.id)
        self.db.flush()
        return {"expired": changed, "cloud_mutations": 0}

    def dashboard(self):
        controls = self.controls()
        rollouts = [self.rollout_view(r) for r in self.db.scalars(select(m.Rollout)).all()
                    if in_scope(r.manifest["scope_id"], self.user.grants, self.scopes)]
        exceptions = self.exceptions()
        counts = {k: 0 for k in ("COMPLIANT", "NON_COMPLIANT", "UNKNOWN", "NOT_APPLICABLE")}
        protected, applicable, exempt = set(), set(), set()
        for c in controls:
            # Keep every known-applicable resource in the owning scope in the denominator,
            # even when the latest assessment targeted only a pilot child scope.
            owned_scopes = descendants(c["scope_id"], self.scopes)
            provider = provider_for(c["implementation"]["template_id"])
            for resource in self.snapshot().resources:
                if resource["scope_id"] in owned_scopes and resource["type"].lower() == provider.resource_type.lower():
                    applicable.add((c["id"], resource["id"]))
            assessment = c["latest_assessment"]
            if not assessment:
                continue
            for k, v in assessment["report"]["counts"].items():
                counts[k] += v
            verified_scopes = set()
            for r in rollouts:
                if (r["manifest"]["control_id"] == c["id"] and r["delivery_state"] == "VERIFIED"
                    and r["observation_fresh"] and not r["blockers"] and r["stage"] not in {"CANCELLED", "PAUSED"}):
                    verified_scopes.update(r["manifest"]["scope_ids"])
            for row in assessment["report"]["rows"]:
                if row["result"] == "NOT_APPLICABLE":
                    continue
                pair = (c["id"], row["id"])
                if row["exception"] == "EFFECTIVE" and assessment["current"]:
                    exempt.add(pair)
                elif row["result"] == "COMPLIANT" and row["scope_id"] in verified_scopes and assessment["current"]:
                    protected.add(pair)
        return {"provenance": "DEMO", "controls": len(controls), "assessed": sum(bool(c["latest_assessment"]) for c in controls),
                "configuration_counts": counts, "applicable_pairs": len(applicable), "protected_pairs": len(protected),
                "exempt_pairs": len(exempt), "coverage_percent": round(100 * len(protected) / len(applicable), 1) if applicable else None,
                "exceptions": len(exceptions), "expired": sum(e["disposition"] == "EXPIRED" for e in exceptions),
                "expiring_soon": sum(self.now < aware(datetime.fromisoformat(e["expires_at"]))
                                      <= self.now + timedelta(days=7) for e in exceptions if e["status"] == "APPROVED"),
                "rollouts": len(rollouts), "waiting_approval": sum(r["delivery_state"] == "NOT_EXPORTED" for r in rollouts),
                "drifted": sum(r["delivery_state"] == "DRIFTED" for r in rollouts),
                "denied_runtime_operations": None, "prevented_attacks": None,
                "note": "Coverage counts control-resource pairs with current compliant configuration and matching mock observations. Not live enforcement."}

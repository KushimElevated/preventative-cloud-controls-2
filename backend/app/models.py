from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .domain import utcnow


def uid():
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    role: Mapped[str] = mapped_column(String(40))
    grants: Mapped[list] = mapped_column(JSON)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Scope(Base):
    __tablename__ = "scopes"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    provider: Mapped[str] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(40))
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("scopes.id"), nullable=True)
    native_id: Mapped[str] = mapped_column(String(600))


class Control(Base):
    __tablename__ = "controls"
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=uid)
    scope_id: Mapped[str] = mapped_column(ForeignKey("scopes.id"))
    latest_revision: Mapped[int] = mapped_column(Integer, default=1)
    lifecycle: Mapped[str] = mapped_column(String(30), default="DRAFT")
    lock_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __mapper_args__ = {"version_id_col": lock_version}


class ControlRevision(Base):
    __tablename__ = "control_revisions"
    __table_args__ = (UniqueConstraint("control_id", "revision"),)
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=uid)
    control_id: Mapped[str] = mapped_column(ForeignKey("controls.id"))
    revision: Mapped[int] = mapped_column(Integer)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    content: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Implementation(Base):
    __tablename__ = "implementations"
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=uid)
    revision_id: Mapped[str] = mapped_column(ForeignKey("control_revisions.id"), unique=True)
    template_id: Mapped[str] = mapped_column(String(80))
    document: Mapped[dict] = mapped_column(JSON)
    document_digest: Mapped[str] = mapped_column(String(64))


class PolicyBinding(Base):
    __tablename__ = "policy_bindings"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    scope_id: Mapped[str] = mapped_column(ForeignKey("scopes.id"))
    provider: Mapped[str] = mapped_column(String(16))
    native_id: Mapped[str] = mapped_column(String(600))
    content: Mapped[dict] = mapped_column(JSON)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InventorySnapshot(Base):
    __tablename__ = "inventory_snapshots"
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=uid)
    ordinal: Mapped[int] = mapped_column(Integer, unique=True)
    label: Mapped[str] = mapped_column(String(120))
    resources: Mapped[list] = mapped_column(JSON)
    requests: Mapped[list] = mapped_column(JSON)
    content_digest: Mapped[str] = mapped_column(String(64))
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExceptionRequest(Base):
    __tablename__ = "exceptions"
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=uid)
    control_id: Mapped[str] = mapped_column(ForeignKey("controls.id"))
    scope_id: Mapped[str] = mapped_column(ForeignKey("scopes.id"))
    requester_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    approver_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resource_ids: Mapped[list] = mapped_column(JSON)
    justification: Mapped[str] = mapped_column(Text)
    compensating_controls: Mapped[str] = mapped_column(Text)
    risk_owner: Mapped[str] = mapped_column(String(160))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(40), default="REQUESTED")
    native_status: Mapped[str] = mapped_column(String(40), default="NOT_REQUESTED")
    representation: Mapped[str] = mapped_column(String(40))
    native_reference: Mapped[str | None] = mapped_column(String(600), nullable=True)
    renewal_of: Mapped[str | None] = mapped_column(ForeignKey("exceptions.id"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __mapper_args__ = {"version_id_col": version}


class Assessment(Base):
    __tablename__ = "assessments"
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=uid)
    ordinal: Mapped[int] = mapped_column(Integer, unique=True)
    control_id: Mapped[str] = mapped_column(ForeignKey("controls.id"))
    revision_id: Mapped[str] = mapped_column(ForeignKey("control_revisions.id"))
    implementation_id: Mapped[str] = mapped_column(ForeignKey("implementations.id"))
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("inventory_snapshots.id"))
    scope_id: Mapped[str] = mapped_column(ForeignKey("scopes.id"))
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    context: Mapped[dict] = mapped_column(JSON)
    report: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Rollout(Base):
    __tablename__ = "rollouts"
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=uid)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id"))
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    manifest: Mapped[dict] = mapped_column(JSON)
    manifest_digest: Mapped[str] = mapped_column(String(64))
    stage: Mapped[str] = mapped_column(String(30), default="ASSESSMENT")
    delivery_state: Mapped[str] = mapped_column(String(30), default="NOT_EXPORTED")
    last_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __mapper_args__ = {"version_id_col": version}


class Approval(Base):
    __tablename__ = "approvals"
    __table_args__ = (UniqueConstraint("rollout_id", "actor_id"),)
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=uid)
    rollout_id: Mapped[str] = mapped_column(ForeignKey("rollouts.id"))
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(30))
    decision: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(Text)
    manifest_digest: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Receipt(Base):
    __tablename__ = "receipts"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    rollout_id: Mapped[str] = mapped_column(ForeignKey("rollouts.id"))
    payload: Mapped[dict] = mapped_column(JSON)
    disposition: Mapped[str] = mapped_column(String(40))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=uid)
    actor_id: Mapped[str] = mapped_column(String(80))
    scope_id: Mapped[str | None] = mapped_column(ForeignKey("scopes.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100))
    object_id: Mapped[str] = mapped_column(String(80))
    detail: Mapped[dict] = mapped_column(JSON)
    correlation_id: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

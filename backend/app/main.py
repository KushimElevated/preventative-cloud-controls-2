import hashlib
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import models as m, schemas as s, assistant
from .config import Settings
from .db import make_engine, session_factory
from .domain import DomainError, PROVIDERS, aware, in_scope, utcnow
from .seed import add_snapshot
from .services import Service, record

log = logging.getLogger("controls")


class BodyLimitMiddleware:
    def __init__(self, app, limit=65536):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        messages, total = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            total += len(message.get("body", b""))
            if total > self.limit:
                return await JSONResponse({"detail": "Request body exceeds 64 KiB."}, 413)(scope, receive, send)
            messages.append(message)
            if not message.get("more_body", False):
                break
        async def replay():
            return messages.pop(0) if messages else await receive()
        await self.app(scope, replay, send)


def create_app(settings=None, engine=None, clock=utcnow):
    settings = settings or Settings.from_env()
    settings.validate()
    engine = engine or make_engine(settings.database_url)
    sessions = session_factory(engine)

    @asynccontextmanager
    async def lifespan(app):
        settings.validate()
        yield

    app = FastAPI(title="Cloud Security Control Engineering", version="0.1.0", lifespan=lifespan,
                  description="Local fixture-only platform. No cloud deployment endpoints.", docs_url=None, redoc_url=None)
    app.state.sessions, app.state.clock = sessions, clock
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "api", "testserver"])
    app.add_middleware(BodyLimitMiddleware)

    @app.middleware("http")
    async def headers(request, call_next):
        request.state.correlation = str(uuid4())
        response = await call_next(request)
        response.headers.update({"X-Request-ID": request.state.correlation, "X-Content-Type-Options": "nosniff",
                                 "Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
        log.info("request method=%s status=%s correlation=%s", request.method, response.status_code, request.state.correlation)
        return response

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        is_assistant = request.url.path.startswith("/api/assistant/")
        if exc.status in {401, 403} or is_assistant:
            with sessions.begin() as db:
                db.add(m.AuditEvent(actor_id=getattr(request.state, "actor", "anonymous"),
                    action="ASSISTANT_COMMAND_REJECTED" if is_assistant else "AUTHORIZATION_DENIED",
                    object_id="request", scope_id=None, detail={"status": exc.status},
                    correlation_id=getattr(request.state, "correlation", "unknown"), created_at=clock()))
        return JSONResponse({"detail": exc.message, "request_id": getattr(request.state, "correlation", None)}, exc.status)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request, exc):
        if request.url.path.startswith("/api/assistant/"):
            with sessions.begin() as db:
                db.add(m.AuditEvent(actor_id=getattr(request.state, "actor", "anonymous"),
                    action="ASSISTANT_PAYLOAD_REJECTED", object_id="request", scope_id=None,
                    detail={"status": 422}, correlation_id=getattr(request.state, "correlation", "unknown"), created_at=clock()))
            return JSONResponse({"detail": "Assistant payload is outside the allowed contract."}, 422)
        return await request_validation_exception_handler(request, exc)

    @app.exception_handler(StaleDataError)
    @app.exception_handler(IntegrityError)
    async def conflict(request, exc):
        if request.url.path.startswith("/api/assistant/"):
            with sessions.begin() as db:
                db.add(m.AuditEvent(actor_id=getattr(request.state, "actor", "anonymous"),
                    action="ASSISTANT_COMMAND_REJECTED", object_id="request", scope_id=None,
                    detail={"status": 409, "reason": "concurrent_change"},
                    correlation_id=getattr(request.state, "correlation", "unknown"), created_at=clock()))
        return JSONResponse({"detail": "Concurrent change or relational conflict. Reload and retry."}, 409)

    def get_db():
        with sessions() as db:
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    Db = Annotated[Session, Depends(get_db, scope="function")]
    bearer = HTTPBearer(auto_error=False)

    def current_user(request: Request, db: Db,
                     credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
        if not credentials:
            raise DomainError("A local demo session is required.", 401)
        token_hash = hashlib.sha256(credentials.credentials.encode()).hexdigest()
        session = db.get(m.AuthSession, token_hash)
        if not session or aware(session.expires_at) <= clock():
            raise DomainError("Session expired or invalid.", 401)
        user = db.get(m.User, session.user_id)
        if not user:
            raise DomainError("Identity no longer exists.", 401)
        request.state.actor = user.id
        return user

    def service(request: Request, db: Db, user: Annotated[m.User, Depends(current_user)]):
        return Service(db, user, clock(), settings, request.state.correlation)

    Svc = Annotated[Service, Depends(service)]

    @app.get("/health")
    def health(db: Db):
        db.execute(text("SELECT 1"))
        return {"status": "ok", "mode": "DEMO_ONLY", "live_deployment": False}

    @app.get("/api/auth/demo-users")
    def users(db: Db):
        return [{"id": u.id, "name": u.name, "role": u.role} for u in db.scalars(select(m.User)).all()]

    @app.post("/api/auth/demo")
    def login(data: s.Login, db: Db, request: Request):
        user = db.get(m.User, data.user_id)
        if not user:
            raise DomainError("Unknown demo identity.", 401)
        token = secrets.token_urlsafe(32)
        db.add(m.AuthSession(token_hash=hashlib.sha256(token.encode()).hexdigest(), user_id=user.id,
                             expires_at=clock()+timedelta(hours=settings.session_hours)))
        db.add(m.AuditEvent(actor_id=user.id, action="DEMO_LOGIN", object_id=user.id, scope_id=None,
                           detail={"mode": "DEMO"}, correlation_id=request.state.correlation, created_at=clock()))
        return {"access_token": token, "token_type": "bearer", "user": record(user)}

    @app.get("/api/me")
    def me(svc: Svc):
        return record(svc.user)

    @app.post("/api/auth/logout", status_code=204)
    def logout(db: Db, svc: Svc, credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer)]):
        obj = db.get(m.AuthSession, hashlib.sha256(credentials.credentials.encode()).hexdigest())
        if obj:
            db.delete(obj)
        return Response(status_code=204)

    @app.get("/api/scopes")
    def scopes(svc: Svc):
        return [v for v in svc.scopes.values() if in_scope(v["id"], svc.user.grants, svc.scopes)]

    @app.get("/api/providers")
    def providers(svc: Svc):
        return [{**p.capabilities(), "document": p.document} for p in PROVIDERS.values()]

    @app.get("/api/dashboard")
    def dashboard(svc: Svc):
        return svc.dashboard()

    @app.get("/api/assistant/catalog")
    def assistant_catalog(svc: Svc):
        svc.permission("read")
        return {"catalog_id": assistant.CATALOG, "protocol": assistant.VERSION,
                "surface_schema": assistant.SurfaceBundle.model_json_schema(), "mode": "DETERMINISTIC"}

    @app.post("/api/assistant/surfaces")
    def assistant_surface(data: assistant.SurfaceQuery, svc: Svc):
        return assistant.render(svc, data)

    @app.post("/api/assistant/commands")
    def assistant_command(data: assistant.Command, svc: Svc):
        return assistant.execute(svc, data)

    @app.post("/api/assistant/intents/{key}/confirm", status_code=201)
    def assistant_confirm(key: str, data: assistant.HumanConfirmation, svc: Svc):
        return assistant.confirm_exception(svc, key, data)

    @app.get("/api/controls")
    def controls(svc: Svc, offset: int = 0, limit: int = 50):
        values = svc.controls()
        return {"items": values[max(offset, 0):max(offset, 0)+min(max(limit, 1), 100)], "total": len(values)}

    @app.post("/api/controls", status_code=201)
    def create_control(data: s.ControlInput, svc: Svc):
        return svc.create_control(data)

    @app.get("/api/controls/{key}")
    def control(key: str, svc: Svc):
        obj = svc.control(key)
        result = svc.control_view(obj)
        result["revisions"] = [record(r) for r in svc.db.scalars(select(m.ControlRevision)
                                .where(m.ControlRevision.control_id == key).order_by(m.ControlRevision.revision.desc())).all()]
        result["exceptions"] = svc.exceptions(key)
        result["baseline"] = svc.context(obj, obj.scope_id)["baseline"]
        return result

    @app.post("/api/controls/{key}/revisions", status_code=201)
    def revise(key: str, data: s.RevisionInput, svc: Svc):
        return svc.revise(key, data)

    @app.post("/api/controls/{key}/retire")
    def retire(key: str, svc: Svc):
        return svc.retire(key)

    @app.delete("/api/controls/{key}", status_code=204)
    def delete(key: str, svc: Svc):
        svc.delete_draft(key)
        return Response(status_code=204)

    @app.post("/api/controls/{key}/assessments", status_code=201)
    def assessment(key: str, data: s.AssessmentInput, svc: Svc):
        return svc.run_assessment(key, data.scope_id)

    @app.get("/api/assessments/{key}")
    def get_assessment(key: str, svc: Svc):
        obj = svc.get(m.Assessment, key)
        svc.access(obj.scope_id)
        return svc.assessment_view(obj)

    @app.get("/api/inventory")
    def inventory(svc: Svc):
        obj = svc.snapshot()
        return {"id": obj.id, "label": obj.label, "collected_at": obj.collected_at,
                "resources": [r for r in obj.resources if in_scope(r["scope_id"], svc.user.grants, svc.scopes)]}

    @app.post("/api/demo/inventory", status_code=201)
    def demo_inventory(data: s.DemoSnapshotInput, svc: Svc):
        svc.permission("admin")
        # Only the seeded estate administrator can replace a whole-estate demo snapshot.
        for root in ["az-root", "aws-root"]:
            svc.access(root)
        obj = add_snapshot(svc.db, data.scenario == "ready", now=svc.now)
        svc.audit("DEMO_SNAPSHOT_ADDED", obj.id, "az-root", {"scenario": data.scenario, "cloud_mutations": 0})
        return {"id": obj.id, "label": obj.label}

    @app.get("/api/exceptions")
    def exceptions(svc: Svc, offset: int = 0, limit: int = 50):
        items = svc.exceptions()
        return {"items": items[max(0, offset):max(0, offset)+min(max(1, limit), 100)], "total": len(items)}

    @app.post("/api/exceptions", status_code=201)
    def exception(data: s.ExceptionInput, svc: Svc):
        return svc.create_exception(data)

    @app.post("/api/exceptions/{key}/decision")
    def decide_exception(key: str, data: s.ExceptionDecision, svc: Svc):
        return svc.decide_exception(key, data)

    @app.post("/api/exceptions/{key}/mock-native-receipt")
    def native_exception(key: str, data: s.NativeException, svc: Svc):
        return svc.native_exception(key, data)

    @app.get("/api/rollouts")
    def rollouts(svc: Svc, offset: int = 0, limit: int = 50):
        rows = [svc.rollout_view(r) for r in svc.db.scalars(select(m.Rollout).order_by(m.Rollout.created_at.desc())).all()
                if in_scope(r.manifest["scope_id"], svc.user.grants, svc.scopes)]
        return {"items": rows[max(0, offset):max(0, offset)+min(max(1, limit), 100)], "total": len(rows)}

    @app.post("/api/rollouts", status_code=201)
    def rollout(data: s.RolloutInput, svc: Svc):
        return svc.create_rollout(data)

    @app.get("/api/rollouts/{key}")
    def get_rollout(key: str, svc: Svc):
        return svc.rollout_view(svc.rollout(key))

    @app.post("/api/rollouts/{key}/approvals")
    def approve(key: str, data: s.ApprovalInput, svc: Svc):
        return svc.approve(key, data)

    @app.post("/api/rollouts/{key}/transition")
    def transition(key: str, data: s.TransitionInput, svc: Svc):
        return svc.transition(key, data)

    @app.post("/api/rollouts/{key}/export")
    def export(key: str, svc: Svc, draft: bool = False):
        return svc.export(key, draft)

    @app.post("/api/rollouts/{key}/mock-receipts")
    def receipt(key: str, data: s.ReceiptInput, svc: Svc):
        return svc.receive(key, data)

    @app.get("/api/rollouts/{key}/receipts")
    def receipts(key: str, svc: Svc):
        svc.rollout(key)
        return [record(r) for r in svc.db.scalars(select(m.Receipt).where(m.Receipt.rollout_id == key)).all()]

    @app.post("/api/reconcile")
    def reconcile(svc: Svc):
        return svc.reconcile()

    @app.get("/api/audit")
    def audit(svc: Svc, offset: int = 0, limit: int = 50):
        rows = [record(a) for a in svc.db.scalars(select(m.AuditEvent).order_by(m.AuditEvent.created_at.desc())).all()
                if (a.scope_id and in_scope(a.scope_id, svc.user.grants, svc.scopes))
                or (a.scope_id is None and (a.actor_id == svc.user.id or svc.user.role == "ADMIN"))]
        return {"items": rows[max(0, offset):max(0, offset)+min(max(1, limit), 100)], "total": len(rows)}

    return app


app = create_app()

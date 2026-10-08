import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.config import Settings
from app.db import make_engine, session_factory
from app.main import create_app
from app.seed import seed


@pytest.fixture
def rig(tmp_path, monkeypatch):
    admin_url = os.getenv("TEST_DATABASE_URL")
    admin = None
    if admin_url:
        # TEST_DATABASE_URL must point at a disposable test instance, never production.
        admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        db_name = "test_controls_" + uuid4().hex
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
        url = str(admin.url.set(database=db_name).render_as_string(hide_password=False))
    else:
        url = f"sqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.delenv("MIGRATION_DATABASE_URL", raising=False)
    command.upgrade(Config("alembic.ini"), "head")
    engine = make_engine(url)
    now = [datetime(2026, 10, 8, 12, tzinfo=timezone.utc)]
    sessions = session_factory(engine)
    with sessions.begin() as db:
        seed(db, now[0])
    app = create_app(Settings(database_url=url, app_env="test"), engine=engine, clock=lambda: now[0])
    with TestClient(app) as client:
        def login(user="engineer"):
            r = client.post("/api/auth/demo", json={"user_id": user})
            assert r.status_code == 200, r.text
            client.headers["Authorization"] = "Bearer " + r.json()["access_token"]
        login()
        yield client, login, now, sessions, engine
    engine.dispose()
    if admin is not None:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE "{db_name}" WITH (FORCE)'))
        admin.dispose()


def ready_plan(rig):
    client, login, now, *_ = rig
    login("admin")
    response = client.post("/api/demo/inventory", json={"scenario": "ready"})
    assert response.status_code == 201, response.text
    login("engineer")
    response = client.post("/api/controls/azure-search/assessments", json={"scope_id": "az-prod"})
    assert response.status_code == 201, response.text
    assessment = response.json()
    assert assessment["report"]["ready"], assessment["report"]
    response = client.post("/api/rollouts", json={"assessment_id": assessment["id"],
        "rollback": "Cloud Engineering reviews the previous assignment and restores it through the existing pipeline.",
        "reason": "Demo pilot with synthetic readiness evidence."})
    assert response.status_code == 201, response.text
    return response.json()


def approved_plan(rig):
    client, login, *_ = rig
    obj = ready_plan(rig)
    for who in ["security", "cloud"]:
        login(who)
        response = client.post(f"/api/rollouts/{obj['id']}/approvals", json={"decision": "APPROVED",
            "reason": "Reviewed this exact synthetic package.", "expected_version": obj["version"]})
        assert response.status_code == 200, response.text
        obj = response.json()
    login("engineer")
    for stage in ["OBSERVATION", "PILOT"]:
        response = client.post(f"/api/rollouts/{obj['id']}/transition", json={"stage": stage, "expected_version": obj["version"]})
        assert response.status_code == 200, response.text
        obj = response.json()
    response = client.post(f"/api/rollouts/{obj['id']}/export")
    assert response.status_code == 200, response.text
    return obj, response.json()

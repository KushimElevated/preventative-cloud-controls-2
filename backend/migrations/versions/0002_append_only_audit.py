"""Protect append-only evidence and audit history at the database boundary."""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None
TABLES = ["audit_events", "control_revisions", "implementations", "inventory_snapshots", "assessments", "approvals", "receipts"]


def upgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE FUNCTION reject_history_update() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'immutable history'; END; $$")
        for table in TABLES:
            # Draft deletion is handled with referential checks. Only audit is never deletable.
            operations = "UPDATE OR DELETE" if table == "audit_events" else "UPDATE"
            op.execute(f"CREATE TRIGGER immutable_{table} BEFORE {operations} ON {table} FOR EACH ROW EXECUTE FUNCTION reject_history_update()")
        op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='controls_app') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO controls_app;
            REVOKE UPDATE, DELETE ON audit_events FROM controls_app;
            REVOKE UPDATE ON control_revisions, implementations, inventory_snapshots, assessments, approvals, receipts FROM controls_app;
            REVOKE ALL ON alembic_version FROM controls_app;
        END IF; END $$""")
    elif op.get_bind().dialect.name == "sqlite":
        for table in TABLES:
            op.execute(f"CREATE TRIGGER immutable_{table} BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT, 'immutable history'); END")
        op.execute("CREATE TRIGGER immutable_audit_delete BEFORE DELETE ON audit_events BEGIN SELECT RAISE(ABORT, 'immutable history'); END")


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        for table in TABLES:
            op.execute(f"DROP TRIGGER immutable_{table} ON {table}")
        op.execute("DROP FUNCTION reject_history_update()")
    elif op.get_bind().dialect.name == "sqlite":
        for table in TABLES:
            op.execute(f"DROP TRIGGER immutable_{table}")
        op.execute("DROP TRIGGER immutable_audit_delete")

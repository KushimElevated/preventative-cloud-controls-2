"""Persist actor-bound, expiring human confirmation intents."""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("assistant_intents",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("actor_id", sa.String(80), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assessment_id", sa.String(80), sa.ForeignKey("assessments.id"), nullable=False),
        sa.Column("expected_revision", sa.Integer(), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("resource_ids", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result_id", sa.String(80), sa.ForeignKey("exceptions.id"), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False))
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'controls_app') THEN "
                   "GRANT SELECT, INSERT, UPDATE ON assistant_intents TO controls_app; END IF; END $$")
    # Existing demo databases get the optional pilot scope; immutable historical snapshots stay intact.
    bind = op.get_bind()
    scopes = sa.table("scopes", *(sa.column(n, sa.String()) for n in
                      ["id", "name", "provider", "kind", "parent_id", "native_id"]))
    if bind.execute(sa.select(scopes.c.id).where(scopes.c.id == "az-prod")).first():
        if not bind.execute(sa.select(scopes.c.id).where(scopes.c.id == "az-search-pilot")).first():
            bind.execute(scopes.insert().values(id="az-search-pilot", name="Azure · Search pilot resource group",
                provider="AZURE", kind="RESOURCE_GROUP", parent_id="az-prod",
                native_id="/subscriptions/00000000-0000-4000-8000-000000000001/resourceGroups/search-pilot"))


def downgrade():
    op.drop_table("assistant_intents")

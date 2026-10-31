"""Tenancy: organizations, memberships, audit events, RLS.

Revision ID: 0001
Revises:
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = ("memberships", "audit_events")


def _app_role() -> str:
    role: str = context.get_context().opts["app_role"]
    if not role.replace("_", "").isalnum():
        raise ValueError(f"invalid app role name: {role!r}")
    return role


def upgrade() -> None:
    app_role = _app_role()
    op.execute(
        f"""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{app_role}') THEN
            RAISE EXCEPTION 'App role "{app_role}" does not exist. Create it first '
              '(see infra/postgres/create_app_role.sql).';
          END IF;
        END $$;
        """
    )
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "organizations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("clerk_org_id", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(200)),
        sa.Column(
            "settings", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "memberships",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("clerk_user_id", sa.String(64), nullable=False),
        sa.Column("email", sa.String(320)),
        sa.Column("display_name", sa.String(200)),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("org_id", "clerk_user_id"),
        sa.CheckConstraint("role IN ('owner', 'editor', 'viewer')", name="role_valid"),
    )
    op.create_index("ix_memberships_org_id", "memberships", ["org_id"])
    op.create_table(
        "audit_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("actor_clerk_user_id", sa.String(64)),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(64)),
        sa.Column("target_id", sa.String(64)),
        sa.Column(
            "details", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_audit_events_org_created", "audit_events", ["org_id", "created_at"])

    # Current tenant, from SET LOCAL app.org_id. Unset or empty -> NULL -> no rows match.
    op.execute(
        """
        CREATE FUNCTION sqa_current_org() RETURNS uuid
        LANGUAGE sql STABLE AS
        $$ SELECT NULLIF(current_setting('app.org_id', true), '')::uuid $$
        """
    )

    # RLS. FORCE applies policies to the table owner too.
    op.execute("ALTER TABLE organizations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE organizations FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON organizations "
        "USING (id = sqa_current_org()) WITH CHECK (id = sqa_current_org())"
    )
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            "USING (org_id = sqa_current_org()) WITH CHECK (org_id = sqa_current_org())"
        )

    # The migration owner may look up orgs without a tenant context. This is
    # only reachable by the app through sqa_ensure_org below.
    op.execute(
        """
        DO $$ BEGIN
          EXECUTE format(
            'CREATE POLICY owner_resolve ON organizations TO %I USING (true) WITH CHECK (true)',
            current_user);
        END $$;
        """
    )
    op.execute(
        """
        CREATE FUNCTION sqa_ensure_org(p_clerk_org_id text, p_name text) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS
        $$
        DECLARE v_id uuid;
        BEGIN
          SELECT id INTO v_id FROM organizations WHERE clerk_org_id = p_clerk_org_id;
          IF v_id IS NULL THEN
            INSERT INTO organizations (clerk_org_id, name)
            VALUES (p_clerk_org_id, left(p_name, 200))
            ON CONFLICT (clerk_org_id) DO NOTHING
            RETURNING id INTO v_id;
            IF v_id IS NULL THEN
              SELECT id INTO v_id FROM organizations WHERE clerk_org_id = p_clerk_org_id;
            END IF;
          END IF;
          RETURN v_id;
        END
        $$
        """
    )

    # Least privilege for the app role.
    op.execute(f"GRANT USAGE ON SCHEMA public TO {app_role}")
    op.execute(f"GRANT SELECT, UPDATE ON organizations TO {app_role}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON memberships TO {app_role}")
    op.execute(f"GRANT SELECT, INSERT ON audit_events TO {app_role}")  # append-only
    op.execute("REVOKE ALL ON FUNCTION sqa_ensure_org(text, text) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION sqa_ensure_org(text, text) TO {app_role}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS sqa_ensure_org(text, text)")
    op.drop_table("audit_events")
    op.drop_table("memberships")
    op.drop_table("organizations")
    op.execute("DROP FUNCTION IF EXISTS sqa_current_org()")

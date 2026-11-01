"""Questionnaires and their extracted questions.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("questionnaires", "questions")


def _app_role() -> str:
    role: str = context.get_context().opts["app_role"]
    if not role.replace("_", "").isalnum():
        raise ValueError(f"invalid app role name: {role!r}")
    return role


def _id() -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def _org() -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        "org_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )


def _created() -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


def upgrade() -> None:
    app_role = _app_role()
    op.create_table(
        "questionnaires",
        _id(),
        _org(),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("error_code", sa.String(32)),
        sa.Column("extractor", sa.String(32)),
        sa.Column("mapping", postgresql.JSONB),
        sa.Column("preview", postgresql.JSONB),
        sa.Column("question_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("uploaded_by", sa.String(64)),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        _created(),
        sa.UniqueConstraint("org_id", "id", name="uq_questionnaires_org_id_id"),
        sa.UniqueConstraint("org_id", "sha256", name="uq_questionnaires_org_sha256"),
        sa.CheckConstraint(
            "kind IN ('xlsx', 'csv', 'docx', 'pdf', 'xml', 'image')", name="kind_valid"
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'extracting', 'needs_mapping', 'ready', 'failed')",
            name="status_valid",
        ),
    )
    op.create_index("ix_questionnaires_org_id", "questionnaires", ["org_id"])

    op.create_table(
        "questions",
        _id(),
        _org(),
        sa.Column("questionnaire_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("ref", sa.String(64)),
        sa.Column("section", sa.Text),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column(
            "locator", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("excluded", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("edited", sa.Boolean, nullable=False, server_default="false"),
        _created(),
        # A question can only belong to a questionnaire of its own org.
        sa.ForeignKeyConstraint(
            ["org_id", "questionnaire_id"],
            ["questionnaires.org_id", "questionnaires.id"],
            ondelete="CASCADE",
            name="fk_questions_questionnaire_same_org",
        ),
        sa.UniqueConstraint("questionnaire_id", "ordinal"),
    )
    op.create_index("ix_questions_org_id", "questions", ["org_id"])
    op.create_index("ix_questions_org_questionnaire", "questions", ["org_id", "questionnaire_id"])

    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            "USING (org_id = sqa_current_org()) WITH CHECK (org_id = sqa_current_org())"
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {app_role}")


def downgrade() -> None:
    op.drop_table("questions")
    op.drop_table("questionnaires")

"""Documents and chunks with embeddings.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIM = 1024  # frozen copy of sqa.models.EMBEDDING_DIM at this revision
TABLES = ("documents", "document_chunks")


def _app_role() -> str:
    role: str = context.get_context().opts["app_role"]
    if not role.replace("_", "").isalnum():
        raise ValueError(f"invalid app role name: {role!r}")
    return role


def upgrade() -> None:
    app_role = _app_role()
    op.create_table(
        "documents",
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
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("rendition_key", sa.String(512)),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("error_code", sa.String(32)),
        sa.Column("parser", sa.String(32)),
        sa.Column("page_count", sa.Integer),
        sa.Column("chunk_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("uploaded_by", sa.String(64)),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("org_id", "id", name="uq_documents_org_id_id"),
        sa.UniqueConstraint("org_id", "sha256", name="uq_documents_org_sha256"),
        sa.CheckConstraint("kind IN ('pdf', 'docx', 'xlsx')", name="kind_valid"),
        sa.CheckConstraint(
            "status IN ('queued', 'processing', 'ready', 'failed')", name="status_valid"
        ),
    )
    op.create_index("ix_documents_org_id", "documents", ["org_id"])

    op.create_table(
        "document_chunks",
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
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("heading", sa.Text),
        sa.Column("page_start", sa.Integer),
        sa.Column("page_end", sa.Integer),
        sa.Column("sheet", sa.String(200)),
        sa.Column("row_start", sa.Integer),
        sa.Column("row_end", sa.Integer),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
        sa.Column("embedding_model", sa.String(100), nullable=False),
        sa.Column(
            "search_tsv",
            postgresql.TSVECTOR,
            sa.Computed(
                "to_tsvector('english', coalesce(heading, '') || ' ' || text)", persisted=True
            ),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        # Composite FK: a chunk can only point at a document in its own org.
        sa.ForeignKeyConstraint(
            ["org_id", "document_id"],
            ["documents.org_id", "documents.id"],
            ondelete="CASCADE",
            name="fk_chunks_document_same_org",
        ),
        sa.UniqueConstraint("document_id", "ordinal"),
    )
    op.create_index("ix_document_chunks_org_id", "document_chunks", ["org_id"])
    op.create_index("ix_document_chunks_org_document", "document_chunks", ["org_id", "document_id"])
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding ON document_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute("CREATE INDEX ix_document_chunks_tsv ON document_chunks USING gin (search_tsv)")

    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            "USING (org_id = sqa_current_org()) WITH CHECK (org_id = sqa_current_org())"
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {app_role}")


def downgrade() -> None:
    op.drop_table("document_chunks")
    op.drop_table("documents")

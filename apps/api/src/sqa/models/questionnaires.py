import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from sqa.models.base import Base, OrgScoped, TimestampMixin


class QuestionnaireKind(StrEnum):
    XLSX = "xlsx"
    CSV = "csv"
    DOCX = "docx"
    PDF = "pdf"
    XML = "xml"
    IMAGE = "image"


class QuestionnaireStatus(StrEnum):
    QUEUED = "queued"
    EXTRACTING = "extracting"
    # Spreadsheet whose question/answer columns we couldn't identify: the user picks them.
    NEEDS_MAPPING = "needs_mapping"
    READY = "ready"
    FAILED = "failed"


class Questionnaire(Base, OrgScoped, TimestampMixin):
    """An imported questionnaire. Its questions are answered in Phase 2b."""

    __tablename__ = "questionnaires"
    __table_args__ = (
        UniqueConstraint("org_id", "id", name="uq_questionnaires_org_id_id"),
        UniqueConstraint("org_id", "sha256", name="uq_questionnaires_org_sha256"),
        CheckConstraint(
            "kind IN ('xlsx', 'csv', 'docx', 'pdf', 'xml', 'image')", name="kind_valid"
        ),
        CheckConstraint(
            "status IN ('queued', 'extracting', 'needs_mapping', 'ready', 'failed')",
            name="status_valid",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sql_text("gen_random_uuid()")
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=QuestionnaireStatus.QUEUED.value
    )
    error_code: Mapped[str | None] = mapped_column(String(32))
    # Which extractor produced the questions, e.g. "spreadsheet", "pdf-text", "claude-vision".
    extractor: Mapped[str | None] = mapped_column(String(32))
    # Spreadsheet/table column mapping: auto-detected, or chosen by the user.
    mapping: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Sheet previews shown when the user has to choose the mapping.
    preview: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    uploaded_by: Mapped[str | None] = mapped_column(String(64))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Question(Base, OrgScoped, TimestampMixin):
    __tablename__ = "questions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["org_id", "questionnaire_id"],
            ["questionnaires.org_id", "questionnaires.id"],
            ondelete="CASCADE",
            name="fk_questions_questionnaire_same_org",
        ),
        UniqueConstraint("questionnaire_id", "ordinal"),
        Index("ix_questions_org_questionnaire", "org_id", "questionnaire_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sql_text("gen_random_uuid()")
    )
    questionnaire_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    # Control or question id as printed, e.g. "IAM-14.1" or "3.2".
    ref: Mapped[str | None] = mapped_column(String(64))
    section: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Where the question (and its answer slot) sits in the original file, so
    # export can write the answer back: {"sheet", "row", "answer_cell"},
    # {"table", "row", "answer_col"}, {"paragraph"} or {"page"}.
    locator: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'{}'::jsonb")
    )
    # Reviewer said this isn't a real question (instructions, a heading...).
    excluded: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    # Reviewer corrected the extracted text.
    edited: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

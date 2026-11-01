"""Questionnaire import and review of the extracted questions."""

import hashlib
import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from sqa.auth.deps import Editor, OrgContext, TenantSession, Viewer
from sqa.core.logging import get_logger
from sqa.db.session import Database
from sqa.ingestion.types import IngestError
from sqa.models import Question, Questionnaire, QuestionnaireKind, QuestionnaireStatus
from sqa.questionnaires.readers import detect_kind
from sqa.queue import JobQueue
from sqa.routes.documents import (
    DatabaseDep,
    QueueDep,
    SettingsDep,
    StoreDep,
    check_writable,
    read_upload,
    rejection,
)
from sqa.schemas.questionnaires import (
    MappingIn,
    QuestionnaireDetailOut,
    QuestionnaireOut,
    QuestionnaireUploadOut,
    QuestionOut,
    QuestionPage,
    QuestionPatch,
)
from sqa.services import audit
from sqa.storage import document_key

router = APIRouter(prefix="/v1/questionnaires", tags=["questionnaires"])
log = get_logger(__name__)

SUPPORTED = "XLSX, CSV, DOCX, PDF, XML, PNG and JPEG"
_EXTENSION = {
    QuestionnaireKind.XLSX: "xlsx",
    QuestionnaireKind.CSV: "csv",
    QuestionnaireKind.DOCX: "docx",
    QuestionnaireKind.PDF: "pdf",
    QuestionnaireKind.XML: "xml",
    QuestionnaireKind.IMAGE: "img",
}


async def _get(
    session: TenantSession, ctx: OrgContext, questionnaire_id: uuid.UUID
) -> Questionnaire:
    record = await session.scalar(
        select(Questionnaire).where(
            Questionnaire.id == questionnaire_id, Questionnaire.org_id == ctx.org_id
        )
    )
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Questionnaire not found")
    return record


@router.get("")
async def list_questionnaires(ctx: Viewer, session: TenantSession) -> list[QuestionnaireOut]:
    rows = await session.scalars(
        select(Questionnaire)
        .where(Questionnaire.org_id == ctx.org_id)
        .order_by(Questionnaire.created_at.desc())
        .limit(500)
    )
    return [QuestionnaireOut.model_validate(r) for r in rows]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={200: {"description": "Same file already imported", "model": QuestionnaireUploadOut}},
)
async def upload_questionnaire(
    ctx: Editor,
    file: UploadFile,
    response: Response,
    settings: SettingsDep,
    db: DatabaseDep,
    store: StoreDep,
    queue: QueueDep,
) -> QuestionnaireUploadOut:
    check_writable(ctx, settings)
    data, filename = await read_upload(file, settings)
    try:
        kind, content_type = detect_kind(filename, data)
    except IngestError as exc:
        raise rejection(exc.code, SUPPORTED) from None

    sha256 = hashlib.sha256(data).hexdigest()
    existing = await _find_by_hash(db, ctx.org_id, sha256)
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return QuestionnaireUploadOut(questionnaire=existing, duplicate=True)

    questionnaire_id = uuid.uuid4()
    key = document_key(ctx.org_id, questionnaire_id, f"questionnaire.{_EXTENSION[kind]}")
    await store.put(key, data, content_type)
    try:
        async with db.tenant(ctx.org_id) as session:
            session.add(
                Questionnaire(
                    id=questionnaire_id,
                    org_id=ctx.org_id,
                    filename=filename,
                    kind=kind.value,
                    content_type=content_type,
                    size_bytes=len(data),
                    sha256=sha256,
                    storage_key=key,
                    uploaded_by=ctx.user_id,
                )
            )
            await audit.record(
                session,
                org_id=ctx.org_id,
                action="questionnaire.uploaded",
                actor_clerk_user_id=ctx.user_id,
                target_type="questionnaire",
                target_id=str(questionnaire_id),
                details={"kind": kind.value, "size_bytes": len(data)},
            )
    except IntegrityError:
        await store.delete(key)
        existing = await _find_by_hash(db, ctx.org_id, sha256)
        if existing is None:
            raise
        response.status_code = status.HTTP_200_OK
        return QuestionnaireUploadOut(questionnaire=existing, duplicate=True)
    except BaseException:
        await store.delete(key)
        raise

    await _enqueue(db, queue, ctx.org_id, questionnaire_id)
    async with db.tenant(ctx.org_id) as session:
        record = await session.get(Questionnaire, questionnaire_id)
        assert record is not None
        return QuestionnaireUploadOut(
            questionnaire=QuestionnaireOut.model_validate(record), duplicate=False
        )


async def _find_by_hash(db: Database, org_id: uuid.UUID, sha256: str) -> QuestionnaireOut | None:
    async with db.tenant(org_id) as session:
        record = await session.scalar(
            select(Questionnaire).where(
                Questionnaire.org_id == org_id, Questionnaire.sha256 == sha256
            )
        )
        return QuestionnaireOut.model_validate(record) if record else None


async def _enqueue(
    db: Database, queue: JobQueue, org_id: uuid.UUID, questionnaire_id: uuid.UUID
) -> None:
    try:
        await queue.enqueue_extract(org_id, questionnaire_id)
    except Exception as exc:
        log.error("enqueue_failed", job_id=str(questionnaire_id), exc_info=exc)
        async with db.tenant(org_id) as session:
            record = await session.get(Questionnaire, questionnaire_id)
            if record is not None:
                record.status = QuestionnaireStatus.FAILED
                record.error_code = "queue_unavailable"


@router.get("/{questionnaire_id}")
async def get_questionnaire(
    questionnaire_id: uuid.UUID, ctx: Viewer, session: TenantSession
) -> QuestionnaireDetailOut:
    return QuestionnaireDetailOut.model_validate(await _get(session, ctx, questionnaire_id))


@router.get("/{questionnaire_id}/questions")
async def list_questions(
    questionnaire_id: uuid.UUID,
    ctx: Viewer,
    session: TenantSession,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> QuestionPage:
    await _get(session, ctx, questionnaire_id)
    where = (Question.org_id == ctx.org_id, Question.questionnaire_id == questionnaire_id)
    total = await session.scalar(select(func.count()).select_from(Question).where(*where))
    rows = await session.scalars(
        select(Question).where(*where).order_by(Question.ordinal).offset(offset).limit(limit)
    )
    return QuestionPage(items=[QuestionOut.model_validate(q) for q in rows], total=total or 0)


@router.put("/{questionnaire_id}/mapping", status_code=status.HTTP_202_ACCEPTED)
async def set_mapping(
    questionnaire_id: uuid.UUID,
    body: MappingIn,
    ctx: Editor,
    settings: SettingsDep,
    db: DatabaseDep,
    queue: QueueDep,
) -> QuestionnaireDetailOut:
    """Choose the question/answer columns by hand, then re-extract with them."""
    check_writable(ctx, settings)
    async with db.tenant(ctx.org_id) as session:
        record = await _get(session, ctx, questionnaire_id)
        if record.kind not in (
            QuestionnaireKind.XLSX,
            QuestionnaireKind.CSV,
            QuestionnaireKind.DOCX,
        ):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Only spreadsheets and tables have columns."
            )
        record.mapping = {"sheets": [m.model_dump() for m in body.sheets], "source": "user"}
        record.status = QuestionnaireStatus.QUEUED
        await audit.record(
            session,
            org_id=ctx.org_id,
            action="questionnaire.mapped",
            actor_clerk_user_id=ctx.user_id,
            target_type="questionnaire",
            target_id=str(questionnaire_id),
        )
    await _enqueue(db, queue, ctx.org_id, questionnaire_id)
    async with db.tenant(ctx.org_id) as session:
        return QuestionnaireDetailOut.model_validate(await _get(session, ctx, questionnaire_id))


@router.post("/{questionnaire_id}/reextract", status_code=status.HTTP_202_ACCEPTED)
async def reextract(
    questionnaire_id: uuid.UUID,
    ctx: Editor,
    settings: SettingsDep,
    db: DatabaseDep,
    queue: QueueDep,
) -> QuestionnaireDetailOut:
    """Run extraction again with automatic detection (discards a manual mapping and edits)."""
    check_writable(ctx, settings)
    async with db.tenant(ctx.org_id) as session:
        record = await _get(session, ctx, questionnaire_id)
        record.mapping = None
        record.status = QuestionnaireStatus.QUEUED
    await _enqueue(db, queue, ctx.org_id, questionnaire_id)
    async with db.tenant(ctx.org_id) as session:
        return QuestionnaireDetailOut.model_validate(await _get(session, ctx, questionnaire_id))


@router.patch("/{questionnaire_id}/questions/{question_id}")
async def update_question(
    questionnaire_id: uuid.UUID,
    question_id: uuid.UUID,
    body: QuestionPatch,
    ctx: Editor,
    session: TenantSession,
    settings: SettingsDep,
) -> QuestionOut:
    """Fix extraction mistakes: correct a question's text or exclude a non-question."""
    check_writable(ctx, settings)
    question = await session.scalar(
        select(Question).where(
            Question.id == question_id,
            Question.questionnaire_id == questionnaire_id,
            Question.org_id == ctx.org_id,
        )
    )
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found")
    if body.text is not None and body.text != question.text:
        question.text = body.text
        question.edited = True
    if body.excluded is not None:
        question.excluded = body.excluded
    await audit.record(
        session,
        org_id=ctx.org_id,
        action="question.updated",
        actor_clerk_user_id=ctx.user_id,
        target_type="question",
        target_id=str(question_id),
        details={"excluded": question.excluded, "edited": question.edited},
    )
    await session.flush()
    return QuestionOut.model_validate(question)


@router.delete("/{questionnaire_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_questionnaire(
    questionnaire_id: uuid.UUID,
    ctx: Editor,
    settings: SettingsDep,
    db: DatabaseDep,
    store: StoreDep,
) -> None:
    check_writable(ctx, settings)
    async with db.tenant(ctx.org_id) as session:
        record = await _get(session, ctx, questionnaire_id)
        key = record.storage_key
        await session.delete(record)
        await audit.record(
            session,
            org_id=ctx.org_id,
            action="questionnaire.deleted",
            actor_clerk_user_id=ctx.user_id,
            target_type="questionnaire",
            target_id=str(questionnaire_id),
        )
    try:
        await store.delete(key)
    except Exception as exc:
        log.error("object_delete_failed", job_id=str(questionnaire_id), exc_info=exc)

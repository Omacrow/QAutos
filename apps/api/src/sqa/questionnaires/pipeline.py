"""The extraction job: stored questionnaire -> questions.

Same shape as document ingestion: slow work outside transactions, then one
transaction that replaces the questionnaire's questions, so re-running (after
the user changes the column mapping) is idempotent.
"""

import time
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, insert, select

from sqa.core.config import Settings
from sqa.core.logging import get_logger
from sqa.ingestion.pipeline import IngestDeps
from sqa.ingestion.types import IngestError
from sqa.models import Question, Questionnaire, QuestionnaireKind, QuestionnaireStatus
from sqa.questionnaires.extract import VisionExtractor, extract_questionnaire
from sqa.questionnaires.types import TransientExtractionError
from sqa.services import audit

log = get_logger(__name__)


def make_vision(settings: Settings) -> VisionExtractor | None:
    """The optional Claude engine, only when chosen and configured."""
    if settings.questionnaire_ocr != "claude" or settings.anthropic_api_key is None:
        return None
    import anthropic

    from sqa.questionnaires.vision import ClaudeVisionExtractor

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key.get_secret_value())
    return ClaudeVisionExtractor(client, model=settings.anthropic_model_extract)


async def extract_questions(
    deps: IngestDeps,
    org_id: uuid.UUID,
    questionnaire_id: uuid.UUID,
    *,
    final_attempt: bool = True,
    vision: VisionExtractor | None = None,
) -> str:
    started = time.monotonic()
    db = deps.db
    async with db.tenant(org_id) as session:
        record = await session.scalar(
            select(Questionnaire).where(
                Questionnaire.id == questionnaire_id, Questionnaire.org_id == org_id
            )
        )
        if record is None:
            return "missing"
        record.status = QuestionnaireStatus.EXTRACTING
        record.error_code = None
        kind = QuestionnaireKind(record.kind)
        storage_key, content_type = record.storage_key, record.content_type
        mapping = record.mapping if (record.mapping or {}).get("source") == "user" else None

    try:
        data = await deps.store.get(storage_key)
        extraction = await extract_questionnaire(
            kind,
            data,
            content_type,
            deps.settings,
            user_mapping=mapping,
            vision=vision or make_vision(deps.settings),
        )
        if len(extraction.questions) > deps.settings.max_questionnaire_questions:
            raise IngestError("too_large")
        if not extraction.questions and not extraction.needs_mapping:
            raise IngestError("no_questions")
    except IngestError as exc:
        return await _fail(db, org_id, questionnaire_id, exc.code)
    except TransientExtractionError:
        if not final_attempt:
            raise
        return await _fail(db, org_id, questionnaire_id, "vision_failed")
    except Exception as exc:
        log.error("extract_failed", job_id=str(questionnaire_id), exc_info=exc)
        return await _fail(db, org_id, questionnaire_id, "internal")

    rows: list[dict[str, Any]] = [
        {
            "org_id": org_id,
            "questionnaire_id": questionnaire_id,
            "ordinal": ordinal,
            "ref": q.ref,
            "section": q.section,
            "text": q.text,
            "locator": q.locator,
        }
        for ordinal, q in enumerate(extraction.questions)
    ]
    status = (
        QuestionnaireStatus.NEEDS_MAPPING if extraction.needs_mapping else QuestionnaireStatus.READY
    )
    async with db.tenant(org_id) as session:
        record = await session.scalar(
            select(Questionnaire)
            .where(Questionnaire.id == questionnaire_id, Questionnaire.org_id == org_id)
            .with_for_update()
        )
        if record is None:
            return "missing"
        await session.execute(
            delete(Question).where(
                Question.org_id == org_id, Question.questionnaire_id == questionnaire_id
            )
        )
        if rows:
            await session.execute(insert(Question), rows)
        record.status = status
        record.extractor = extraction.extractor
        if extraction.mapping is not None:
            record.mapping = {**extraction.mapping, "source": "user" if mapping else "detected"}
        record.preview = extraction.preview
        record.question_count = len(rows)
        record.processed_at = datetime.now(UTC)
        await audit.record(
            session,
            org_id=org_id,
            action="questionnaire.extracted",
            actor_clerk_user_id=None,
            target_type="questionnaire",
            target_id=str(questionnaire_id),
            details={"count": len(rows), "extractor": extraction.extractor, "status": status.value},
        )
    log.info(
        "questionnaire_extracted",
        job_id=str(questionnaire_id),
        count=len(rows),
        parser=extraction.extractor,
        status=status.value,
        duration_ms=round((time.monotonic() - started) * 1000),
    )
    return status.value


async def _fail(db: Any, org_id: uuid.UUID, questionnaire_id: uuid.UUID, code: str) -> str:
    async with db.tenant(org_id) as session:
        record = await session.scalar(
            select(Questionnaire).where(
                Questionnaire.id == questionnaire_id, Questionnaire.org_id == org_id
            )
        )
        if record is None:
            return "missing"
        record.status = QuestionnaireStatus.FAILED
        record.error_code = code
        record.processed_at = datetime.now(UTC)
        await audit.record(
            session,
            org_id=org_id,
            action="questionnaire.failed",
            actor_clerk_user_id=None,
            target_type="questionnaire",
            target_id=str(questionnaire_id),
            details={"error_code": code},
        )
    log.warning("questionnaire_failed", job_id=str(questionnaire_id), error_code=code)
    return QuestionnaireStatus.FAILED.value

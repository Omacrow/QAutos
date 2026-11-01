"""Background job dispatch.

`ArqQueue` hands jobs to the arq worker through Redis (production).
`InlineQueue` runs them inside the request: deterministic for tests, and lets
local development work without Redis. Settings refuse it in production.
"""

import uuid
from typing import Any, Protocol

from sqa.ingestion.pipeline import IngestDeps, ingest_document

INGEST_JOB = "ingest_document"
EXTRACT_JOB = "extract_questionnaire"


class JobQueue(Protocol):
    async def enqueue_ingest(self, org_id: uuid.UUID, document_id: uuid.UUID) -> None: ...

    async def enqueue_extract(self, org_id: uuid.UUID, questionnaire_id: uuid.UUID) -> None: ...

    async def aclose(self) -> None: ...


class ArqQueue:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def enqueue_ingest(self, org_id: uuid.UUID, document_id: uuid.UUID) -> None:
        await self._pool.enqueue_job(INGEST_JOB, str(org_id), str(document_id))

    async def enqueue_extract(self, org_id: uuid.UUID, questionnaire_id: uuid.UUID) -> None:
        await self._pool.enqueue_job(EXTRACT_JOB, str(org_id), str(questionnaire_id))

    async def aclose(self) -> None:
        await self._pool.aclose()


class InlineQueue:
    def __init__(self, deps: IngestDeps) -> None:
        self._deps = deps

    async def enqueue_ingest(self, org_id: uuid.UUID, document_id: uuid.UUID) -> None:
        await ingest_document(self._deps, org_id, document_id)

    async def enqueue_extract(self, org_id: uuid.UUID, questionnaire_id: uuid.UUID) -> None:
        from sqa.questionnaires.pipeline import extract_questions

        await extract_questions(self._deps, org_id, questionnaire_id)

    async def aclose(self) -> None:
        pass

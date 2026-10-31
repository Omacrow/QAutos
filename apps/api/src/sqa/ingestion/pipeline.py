"""The ingestion job: stored file -> chunks with embeddings.

Runs in the worker. Slow work (download, parse, embed) happens outside any
database transaction; the result is written in one short transaction, which
replaces earlier chunks, so a re-run is idempotent and readers never see a
half-written document.
"""

import asyncio
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePath
from typing import Any

from sqlalchemy import delete, insert, select

from sqa.core.config import Settings
from sqa.core.logging import get_logger
from sqa.db.session import Database
from sqa.embeddings import Embedder, EmbeddingError, TransientEmbeddingError
from sqa.ingestion.chunking import Chunk, chunk_blocks
from sqa.ingestion.docx import convert_to_pdf, find_soffice, parse_docx
from sqa.ingestion.pdf import parse_pdf
from sqa.ingestion.types import IngestError, ParsedDocument
from sqa.ingestion.xlsx import parse_xlsx
from sqa.models import Document, DocumentChunk, DocumentKind, DocumentStatus
from sqa.services import audit
from sqa.storage import ObjectStore, document_key

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class IngestDeps:
    db: Database
    store: ObjectStore
    embedder: Embedder
    settings: Settings
    soffice: str | None


def make_deps(
    db: Database, store: ObjectStore, embedder: Embedder, settings: Settings
) -> IngestDeps:
    soffice = find_soffice() if settings.docx_converter != "none" else None
    return IngestDeps(db=db, store=store, embedder=embedder, settings=settings, soffice=soffice)


def extract(
    kind: DocumentKind, data: bytes, settings: Settings, soffice: str | None
) -> tuple[ParsedDocument, bytes | None]:
    """Parse a file. Returns the parse and, for DOCX, the PDF rendition if one was made."""
    if kind is DocumentKind.PDF:
        return parse_pdf(data, max_pages=settings.max_document_pages), None
    if kind is DocumentKind.XLSX:
        return parse_xlsx(data, max_rows=settings.max_spreadsheet_rows), None
    if soffice is not None:
        rendition = convert_to_pdf(data, soffice)
        parsed = parse_pdf(
            rendition, max_pages=settings.max_document_pages, parser="libreoffice+pymupdf"
        )
        return parsed, rendition
    if settings.docx_converter == "libreoffice":
        raise IngestError("conversion_failed")  # required but not installed
    return parse_docx(data), None


def embedding_text(title: str, chunk: Chunk) -> str:
    """What gets embedded: the passage plus where it sits, which sharpens retrieval."""
    context = " > ".join((title, *chunk.heading_path))
    if chunk.sheet:
        context += f" (sheet {chunk.sheet})"
    return f"{context}\n\n{chunk.text}"


async def ingest_document(
    deps: IngestDeps,
    org_id: uuid.UUID,
    document_id: uuid.UUID,
    *,
    final_attempt: bool = True,
) -> str:
    """Process one document. Returns the final status.

    A transient embedding failure is re-raised when another attempt will
    follow, so the queue can retry it later.
    """
    started = time.monotonic()
    db = deps.db
    async with db.tenant(org_id) as session:
        doc = await session.scalar(
            select(Document).where(Document.id == document_id, Document.org_id == org_id)
        )
        if doc is None:
            return "missing"  # deleted before we got to it
        doc.status = DocumentStatus.PROCESSING
        doc.error_code = None
        kind = DocumentKind(doc.kind)
        storage_key = doc.storage_key
        title = PurePath(doc.filename).stem

    try:
        data = await deps.store.get(storage_key)
        parsed, rendition = await asyncio.to_thread(
            extract, kind, data, deps.settings, deps.soffice
        )
        chunks = chunk_blocks(parsed.blocks)
        if not chunks:
            raise IngestError("no_text")
        vectors = await deps.embedder.embed_documents([embedding_text(title, c) for c in chunks])
    except IngestError as exc:
        return await _fail(db, org_id, document_id, exc.code)
    except TransientEmbeddingError:
        if not final_attempt:
            raise
        return await _fail(db, org_id, document_id, "embedding_failed")
    except EmbeddingError:
        return await _fail(db, org_id, document_id, "embedding_failed")
    except Exception as exc:
        log.error("ingest_failed", document_id=str(document_id), exc_info=exc)
        return await _fail(db, org_id, document_id, "internal")

    rendition_key = None
    if rendition is not None:
        rendition_key = document_key(org_id, document_id, "rendition.pdf")
        await deps.store.put(rendition_key, rendition, "application/pdf")

    rows: list[dict[str, Any]] = [
        {
            "org_id": org_id,
            "document_id": document_id,
            "ordinal": chunk.ordinal,
            "text": chunk.text,
            "heading": chunk.heading,
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
            "sheet": chunk.sheet,
            "row_start": chunk.row_start,
            "row_end": chunk.row_end,
            "embedding": vector,
            "embedding_model": deps.embedder.model,
        }
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]
    async with db.tenant(org_id) as session:
        doc = await session.scalar(
            select(Document)
            .where(Document.id == document_id, Document.org_id == org_id)
            .with_for_update()
        )
        if doc is None:
            if rendition_key:
                await deps.store.delete(rendition_key)
            return "missing"
        await session.execute(
            delete(DocumentChunk).where(
                DocumentChunk.org_id == org_id, DocumentChunk.document_id == document_id
            )
        )
        await session.execute(insert(DocumentChunk), rows)
        doc.status = DocumentStatus.READY
        doc.parser = parsed.parser
        doc.page_count = parsed.page_count
        doc.chunk_count = len(rows)
        doc.rendition_key = rendition_key
        doc.processed_at = datetime.now(UTC)
        await audit.record(
            session,
            org_id=org_id,
            action="document.processed",
            actor_clerk_user_id=None,
            target_type="document",
            target_id=str(document_id),
            details={
                "chunk_count": len(rows),
                "page_count": parsed.page_count,
                "empty_pages": len(parsed.empty_pages),
            },
        )
    log.info(
        "document_processed",
        document_id=str(document_id),
        chunk_count=len(rows),
        page_count=parsed.page_count,
        parser=parsed.parser,
        duration_ms=round((time.monotonic() - started) * 1000),
    )
    return DocumentStatus.READY.value


async def _fail(db: Database, org_id: uuid.UUID, document_id: uuid.UUID, code: str) -> str:
    async with db.tenant(org_id) as session:
        doc = await session.scalar(
            select(Document).where(Document.id == document_id, Document.org_id == org_id)
        )
        if doc is None:
            return "missing"
        doc.status = DocumentStatus.FAILED
        doc.error_code = code
        doc.processed_at = datetime.now(UTC)
        await audit.record(
            session,
            org_id=org_id,
            action="document.failed",
            actor_clerk_user_id=None,
            target_type="document",
            target_id=str(document_id),
            details={"error_code": code},
        )
    log.warning("document_failed", document_id=str(document_id), error_code=code)
    return DocumentStatus.FAILED.value

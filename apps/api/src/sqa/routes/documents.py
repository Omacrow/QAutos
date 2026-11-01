"""Document upload, listing, chunks, download and deletion.

Uploads go through the API rather than straight to the bucket so every file
is size-checked and type-checked (by its bytes) before it is stored.
"""

import hashlib
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import defer

from sqa.auth.deps import Editor, OrgContext, TenantSession, Viewer, get_database, get_settings_dep
from sqa.core.config import Settings
from sqa.core.logging import get_logger
from sqa.db.session import Database
from sqa.ingestion.types import IngestError
from sqa.ingestion.validate import CONTENT_TYPES, detect_kind, safe_filename
from sqa.models import Document, DocumentChunk, DocumentStatus
from sqa.queue import JobQueue
from sqa.schemas.documents import ChunkOut, ChunkPage, DocumentOut, DownloadOut, UploadOut
from sqa.services import audit
from sqa.storage import ObjectStore, document_key

router = APIRouter(prefix="/v1/documents", tags=["documents"])
log = get_logger(__name__)

SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
DatabaseDep = Annotated[Database, Depends(get_database)]

_REJECTIONS = {
    "unsupported_type": (
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        "Only PDF, DOCX and XLSX files are supported.",
    ),
    "macros_not_allowed": (
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        "Macro-enabled files are not accepted.",
    ),
    "too_large": (status.HTTP_413_CONTENT_TOO_LARGE, "The file is too large."),
    "corrupt": (status.HTTP_400_BAD_REQUEST, "The file appears to be damaged."),
}


def get_store(request: Request) -> ObjectStore:
    store: ObjectStore = request.app.state.store
    return store


def get_queue(request: Request) -> JobQueue:
    queue: JobQueue = request.app.state.queue
    return queue


StoreDep = Annotated[ObjectStore, Depends(get_store)]
QueueDep = Annotated[JobQueue, Depends(get_queue)]


async def read_upload(file: UploadFile, settings: Settings) -> tuple[bytes, str]:
    """The file's bytes (size-checked) and a safe display name."""
    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "The file is too large.")
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The file is empty.")
    return data, safe_filename(file.filename or "")


def rejection(code: str, supported: str = "PDF, DOCX and XLSX") -> HTTPException:
    """HTTP error for a file rejected at upload."""
    status_code, message = _REJECTIONS.get(code, _REJECTIONS["corrupt"])
    if code == "unsupported_type":
        message = f"Only {supported} files are supported."
    return HTTPException(status_code, message)


def check_writable(ctx: OrgContext, settings: Settings) -> None:
    """The shared demo org is read-only unless explicitly opened up."""
    if ctx.clerk_org_id == settings.demo_clerk_org_id and not settings.demo_allow_uploads:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Uploads are turned off in the demo workspace."
        )


async def _get_document(
    session: TenantSession, ctx: OrgContext, document_id: uuid.UUID
) -> Document:
    doc = await session.scalar(
        select(Document).where(Document.id == document_id, Document.org_id == ctx.org_id)
    )
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return doc


@router.get("")
async def list_documents(ctx: Viewer, session: TenantSession) -> list[DocumentOut]:
    rows = await session.scalars(
        select(Document)
        .where(Document.org_id == ctx.org_id)
        .order_by(Document.created_at.desc())
        .limit(500)
    )
    return [DocumentOut.model_validate(d) for d in rows]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={200: {"description": "Same file already uploaded", "model": UploadOut}},
)
async def upload_document(
    ctx: Editor,
    file: UploadFile,
    response: Response,
    settings: SettingsDep,
    db: DatabaseDep,
    store: StoreDep,
    queue: QueueDep,
) -> UploadOut:
    check_writable(ctx, settings)
    data, filename = await read_upload(file, settings)
    try:
        kind = detect_kind(filename, data)
    except IngestError as exc:
        raise rejection(exc.code) from None

    sha256 = hashlib.sha256(data).hexdigest()
    existing = await _find_by_hash(db, ctx.org_id, sha256)
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return UploadOut(document=existing, duplicate=True)

    document_id = uuid.uuid4()
    key = document_key(ctx.org_id, document_id, f"original.{kind.value}")
    await store.put(key, data, CONTENT_TYPES[kind])
    try:
        async with db.tenant(ctx.org_id) as session:
            session.add(
                Document(
                    id=document_id,
                    org_id=ctx.org_id,
                    filename=filename,
                    kind=kind.value,
                    content_type=CONTENT_TYPES[kind],
                    size_bytes=len(data),
                    sha256=sha256,
                    storage_key=key,
                    uploaded_by=ctx.user_id,
                )
            )
            await audit.record(
                session,
                org_id=ctx.org_id,
                action="document.uploaded",
                actor_clerk_user_id=ctx.user_id,
                target_type="document",
                target_id=str(document_id),
                details={"kind": kind.value, "size_bytes": len(data)},
            )
    except IntegrityError:
        # Lost a race with an identical upload.
        await store.delete(key)
        existing = await _find_by_hash(db, ctx.org_id, sha256)
        if existing is None:
            raise
        response.status_code = status.HTTP_200_OK
        return UploadOut(document=existing, duplicate=True)
    except BaseException:
        await store.delete(key)
        raise

    await _enqueue(db, queue, ctx.org_id, document_id)
    async with db.tenant(ctx.org_id) as session:
        doc = await session.get(Document, document_id)
        assert doc is not None
        return UploadOut(document=DocumentOut.model_validate(doc), duplicate=False)


async def _find_by_hash(db: Database, org_id: uuid.UUID, sha256: str) -> DocumentOut | None:
    async with db.tenant(org_id) as session:
        doc = await session.scalar(
            select(Document).where(Document.org_id == org_id, Document.sha256 == sha256)
        )
        return DocumentOut.model_validate(doc) if doc else None


async def _enqueue(
    db: Database, queue: JobQueue, org_id: uuid.UUID, document_id: uuid.UUID
) -> None:
    try:
        await queue.enqueue_ingest(org_id, document_id)
    except Exception as exc:
        # Visible to the user, who can retry with "Reprocess".
        log.error("enqueue_failed", document_id=str(document_id), exc_info=exc)
        async with db.tenant(org_id) as session:
            doc = await session.get(Document, document_id)
            if doc is not None:
                doc.status = DocumentStatus.FAILED
                doc.error_code = "queue_unavailable"


@router.get("/{document_id}")
async def get_document(document_id: uuid.UUID, ctx: Viewer, session: TenantSession) -> DocumentOut:
    return DocumentOut.model_validate(await _get_document(session, ctx, document_id))


@router.get("/{document_id}/chunks")
async def list_chunks(
    document_id: uuid.UUID,
    ctx: Viewer,
    session: TenantSession,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ChunkPage:
    await _get_document(session, ctx, document_id)
    where = (DocumentChunk.org_id == ctx.org_id, DocumentChunk.document_id == document_id)
    total = await session.scalar(select(func.count()).select_from(DocumentChunk).where(*where))
    rows = await session.scalars(
        select(DocumentChunk)
        .options(defer(DocumentChunk.embedding))
        .where(*where)
        .order_by(DocumentChunk.ordinal)
        .offset(offset)
        .limit(limit)
    )
    return ChunkPage(items=[ChunkOut.model_validate(c) for c in rows], total=total or 0)


@router.post("/{document_id}/download")
async def download_document(
    document_id: uuid.UUID,
    ctx: Viewer,
    session: TenantSession,
    settings: SettingsDep,
    store: StoreDep,
    rendition: bool = False,
    inline: bool = False,
) -> DownloadOut:
    """A short-lived link to the original file, or to the PDF rendition of a DOCX.

    `inline` asks the browser to display a PDF (so a citation can open at its
    page) instead of saving it. Other types are always downloaded.
    POST rather than GET: it writes an audit event.
    """
    doc = await _get_document(session, ctx, document_id)
    if rendition:
        if doc.rendition_key is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No PDF rendition")
        key, content_type = doc.rendition_key, "application/pdf"
        filename = f"{doc.filename.rsplit('.', 1)[0]}.pdf"
    else:
        key, content_type, filename = doc.storage_key, doc.content_type, doc.filename
    url = await store.signed_url(
        key,
        filename=filename,
        content_type=content_type,
        expires_in=settings.signed_url_ttl_seconds,
        inline=inline and content_type == "application/pdf",
    )
    await audit.record(
        session,
        org_id=ctx.org_id,
        action="document.downloaded",
        actor_clerk_user_id=ctx.user_id,
        target_type="document",
        target_id=str(document_id),
        details={"rendition": rendition, "inline": inline},
    )
    return DownloadOut(url=url, expires_in=settings.signed_url_ttl_seconds)


@router.post("/{document_id}/reprocess", status_code=status.HTTP_202_ACCEPTED)
async def reprocess_document(
    document_id: uuid.UUID,
    ctx: Editor,
    settings: SettingsDep,
    db: DatabaseDep,
    queue: QueueDep,
) -> DocumentOut:
    check_writable(ctx, settings)
    async with db.tenant(ctx.org_id) as session:
        doc = await _get_document(session, ctx, document_id)
        doc.status = DocumentStatus.QUEUED
        doc.error_code = None
        await audit.record(
            session,
            org_id=ctx.org_id,
            action="document.reprocessed",
            actor_clerk_user_id=ctx.user_id,
            target_type="document",
            target_id=str(document_id),
        )
    await _enqueue(db, queue, ctx.org_id, document_id)
    async with db.tenant(ctx.org_id) as session:
        return DocumentOut.model_validate(await _get_document(session, ctx, document_id))


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    ctx: Editor,
    settings: SettingsDep,
    db: DatabaseDep,
    store: StoreDep,
) -> None:
    """Deletes the document, its chunks (cascade) and its stored files."""
    check_writable(ctx, settings)
    async with db.tenant(ctx.org_id) as session:
        doc = await _get_document(session, ctx, document_id)
        keys = [k for k in (doc.storage_key, doc.rendition_key) if k]
        await session.delete(doc)
        await audit.record(
            session,
            org_id=ctx.org_id,
            action="document.deleted",
            actor_clerk_user_id=ctx.user_id,
            target_type="document",
            target_id=str(document_id),
        )
    for key in keys:
        try:
            await store.delete(key)
        except Exception as exc:
            log.error("object_delete_failed", document_id=str(document_id), exc_info=exc)

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from sqa.models import DocumentKind, DocumentStatus


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    kind: DocumentKind
    size_bytes: int
    status: DocumentStatus
    error_code: str | None
    parser: str | None
    page_count: int | None
    chunk_count: int
    has_rendition: bool
    uploaded_by: str | None
    created_at: datetime
    processed_at: datetime | None


class UploadOut(BaseModel):
    document: DocumentOut
    # True when the same file was already uploaded to this org.
    duplicate: bool


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ordinal: int
    text: str
    heading: str | None
    page_start: int | None
    page_end: int | None
    sheet: str | None
    row_start: int | None
    row_end: int | None


class ChunkPage(BaseModel):
    items: list[ChunkOut]
    total: int


class DownloadOut(BaseModel):
    url: str
    expires_in: int

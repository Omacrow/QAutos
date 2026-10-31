"""Decide what an upload is from its bytes, not from what the client claims."""

import io
import zipfile
from pathlib import PurePath

from sqa.ingestion.types import IngestError
from sqa.models import DocumentKind

CONTENT_TYPES = {
    DocumentKind.PDF: "application/pdf",
    DocumentKind.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    DocumentKind.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
_EXTENSIONS = {".pdf": DocumentKind.PDF, ".docx": DocumentKind.DOCX, ".xlsx": DocumentKind.XLSX}
# The part that proves an OOXML zip is the format its extension says.
_OOXML_MAIN_PART = {DocumentKind.DOCX: "word/document.xml", DocumentKind.XLSX: "xl/workbook.xml"}

# Zip-bomb limits for DOCX/XLSX.
MAX_UNCOMPRESSED_BYTES = 300 * 1024 * 1024
MAX_ZIP_ENTRIES = 10_000
MAX_COMPRESSION_RATIO = 200


def detect_kind(filename: str, data: bytes) -> DocumentKind:
    kind = _EXTENSIONS.get(PurePath(filename).suffix.lower())
    if kind is None:
        raise IngestError("unsupported_type")
    if kind is DocumentKind.PDF:
        # The header may be preceded by a little junk; readers accept up to 1 KB.
        if b"%PDF-" not in data[:1024]:
            raise IngestError("unsupported_type")
        return kind
    _check_ooxml(data, _OOXML_MAIN_PART[kind])
    return kind


def _check_ooxml(data: bytes, main_part: str) -> None:
    if not data.startswith(b"PK\x03\x04"):
        raise IngestError("unsupported_type")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
    except zipfile.BadZipFile:
        raise IngestError("corrupt") from None
    names = {info.filename for info in infos}
    if main_part not in names or "[Content_Types].xml" not in names:
        raise IngestError("unsupported_type")
    if any(name.endswith("vbaProject.bin") for name in names):
        raise IngestError("macros_not_allowed")
    total = sum(info.file_size for info in infos)
    compressed = sum(info.compress_size for info in infos) or 1
    if (
        len(infos) > MAX_ZIP_ENTRIES
        or total > MAX_UNCOMPRESSED_BYTES
        or total / compressed > MAX_COMPRESSION_RATIO
    ):
        raise IngestError("too_large")


def safe_filename(filename: str) -> str:
    """Basename only, printable, at most 255 chars. Used for display and downloads."""
    name = PurePath(filename.replace("\\", "/")).name
    name = "".join(ch for ch in name if ch.isprintable() and ch not in '"<>|*?:')
    return name.strip()[:255] or "document"

"""DOCX extraction.

DOCX has no fixed pages; pagination happens when it is rendered. To cite real
page numbers we render it to PDF with LibreOffice (installed in the worker
image) and parse that PDF. The PDF is kept, so a citation can open that page.

Without LibreOffice (local development), python-docx reads the structure
directly. Headings come from paragraph styles, and pages from the page breaks
Word records when it last saved the file (`w:lastRenderedPageBreak`), which
match what the author saw but can drift for files never opened in Word.
"""

import io
import shutil
import subprocess
import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from docx import Document as load_docx
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from sqa.ingestion.types import Block, IngestError, ParsedDocument

CONVERT_TIMEOUT_SECONDS = 180
_HEADING_STYLES = {"title": 1, "heading 1": 1, "heading 2": 2, "heading 3": 3}


def find_soffice() -> str | None:
    return shutil.which("soffice") or shutil.which("libreoffice")


def convert_to_pdf(data: bytes, soffice: str) -> bytes:
    """Render with LibreOffice in a private profile, so jobs can run in parallel."""
    with tempfile.TemporaryDirectory(prefix="sqa-docx-") as tmp:
        work = Path(tmp)
        source = work / "input.docx"
        source.write_bytes(data)
        profile = (work / f"profile-{uuid.uuid4().hex}").as_uri()
        try:
            subprocess.run(  # noqa: S603 - fixed argv, no shell
                [
                    soffice,
                    f"-env:UserInstallation={profile}",
                    "--headless",
                    "--norestore",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(work),
                    str(source),
                ],
                check=True,
                capture_output=True,
                timeout=CONVERT_TIMEOUT_SECONDS,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            raise IngestError("conversion_failed") from None
        output = work / "input.pdf"
        if not output.exists():
            raise IngestError("conversion_failed")
        return output.read_bytes()


def parse_docx(data: bytes) -> ParsedDocument:
    try:
        document = load_docx(io.BytesIO(data))
    except Exception:
        raise IngestError("corrupt") from None

    blocks: list[Block] = []
    path: list[tuple[int, str]] = []
    page = 1
    for item in _body_items(document):
        if isinstance(item, Paragraph):
            before, after = _page_breaks(item)
            page += before
            text = _clean(item.text)
            level = _heading_level(item)
            if text and level is not None:
                path = [p for p in path if p[0] < level] + [(level, text)]
            elif text:
                blocks.append(Block(text=text, page=page, heading_path=_titles(path)))
            page += after
        else:
            for row in item.rows:
                cells = _unique_cells(row.cells)
                text = " | ".join(c for c in cells if c)
                if text:
                    blocks.append(Block(text=text, page=page, heading_path=_titles(path)))
    if not blocks and not path:
        raise IngestError("no_text")
    return ParsedDocument(blocks=blocks, parser="python-docx", page_count=page)


def _body_items(document: Any) -> Iterator[Paragraph | Table]:
    """Paragraphs and tables in document order (python-docx lists them separately)."""
    body = document.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield Table(child, document)


def _heading_level(paragraph: Paragraph) -> int | None:
    name = (paragraph.style.name if paragraph.style is not None else "") or ""
    return _HEADING_STYLES.get(name.lower())


def _page_breaks(paragraph: Paragraph) -> tuple[int, int]:
    """Page breaks (before, after) this paragraph's text.

    Word often writes a hard break and a rendered break at the same spot, so
    breaks with no text between them count once.
    """
    before = 1 if paragraph.paragraph_format.page_break_before else 0
    after = 0
    seen_text = pending = False
    for element in paragraph._p.iter():
        if element.tag == qn("w:t") and element.text and element.text.strip():
            if pending and seen_text:
                after += 1
            elif pending:
                before = 1
            seen_text, pending = True, False
        elif _is_page_break(element):
            pending = True
    if pending:
        after += 1
    return before, after


def _is_page_break(element: Any) -> bool:
    if element.tag == qn("w:lastRenderedPageBreak"):
        return True
    return bool(element.tag == qn("w:br") and element.get(qn("w:type")) == "page")


def _unique_cells(cells: list[Any]) -> list[str]:
    """Merged cells repeat in python-docx; keep each underlying cell once."""
    seen: set[int] = set()
    out: list[str] = []
    for cell in cells:
        if id(cell._tc) in seen:
            continue
        seen.add(id(cell._tc))
        out.append(_clean(cell.text))
    return out


def _titles(path: list[tuple[int, str]]) -> tuple[str, ...]:
    return tuple(title for _, title in path)


def _clean(text: str) -> str:
    return " ".join(text.split())

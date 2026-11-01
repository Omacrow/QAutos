"""Format detection and readers for each questionnaire format."""

import csv
import io
from pathlib import PurePath
from typing import Any

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
from docx import Document as load_docx
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from openpyxl import load_workbook

from sqa.ingestion.pdf import read_lines
from sqa.ingestion.types import IngestError
from sqa.ingestion.validate import _check_ooxml
from sqa.models import QuestionnaireKind
from sqa.questionnaires.heuristics import (
    clean,
    is_question_sentence,
    looks_like_question,
    split_ref,
)
from sqa.questionnaires.lines import Line
from sqa.questionnaires.tabular import Grid
from sqa.questionnaires.types import ExtractedQuestion

CONTENT_TYPES = {
    QuestionnaireKind.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    QuestionnaireKind.CSV: "text/csv",
    QuestionnaireKind.DOCX: (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
    QuestionnaireKind.PDF: "application/pdf",
    QuestionnaireKind.XML: "application/xml",
}
_IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
_EXTENSIONS = {
    ".xlsx": QuestionnaireKind.XLSX,
    ".csv": QuestionnaireKind.CSV,
    ".docx": QuestionnaireKind.DOCX,
    ".pdf": QuestionnaireKind.PDF,
    ".xml": QuestionnaireKind.XML,
    **{ext: QuestionnaireKind.IMAGE for ext in _IMAGE_TYPES},
}


def detect_kind(filename: str, data: bytes) -> tuple[QuestionnaireKind, str]:
    """(kind, content type), decided from the bytes; the extension only picks the candidate."""
    suffix = PurePath(filename).suffix.lower()
    kind = _EXTENSIONS.get(suffix)
    if kind is None:
        raise IngestError("unsupported_type")
    if kind is QuestionnaireKind.PDF:
        if b"%PDF-" not in data[:1024]:
            raise IngestError("unsupported_type")
    elif kind is QuestionnaireKind.XLSX:
        _check_ooxml(data, "xl/workbook.xml")
    elif kind is QuestionnaireKind.DOCX:
        _check_ooxml(data, "word/document.xml")
    elif kind is QuestionnaireKind.IMAGE:
        png = data.startswith(b"\x89PNG\r\n\x1a\n")
        jpeg = data.startswith(b"\xff\xd8\xff")
        if not (png if suffix == ".png" else jpeg):
            raise IngestError("unsupported_type")
        return kind, _IMAGE_TYPES[suffix]
    elif kind is QuestionnaireKind.CSV:
        _decode_text(data)
    elif kind is QuestionnaireKind.XML and not _decode_text(data).lstrip().startswith("<"):
        raise IngestError("unsupported_type")
    return kind, CONTENT_TYPES[kind]


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16"):
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        if "\x00" not in text:
            return text
    raise IngestError("unsupported_type")


# --- Spreadsheets -------------------------------------------------------------


def xlsx_grids(data: bytes, *, max_rows: int) -> list[tuple[str, Grid]]:
    try:
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception:
        raise IngestError("corrupt") from None
    grids: list[tuple[str, Grid]] = []
    total = 0
    try:
        for sheet in workbook.worksheets:
            if sheet.sheet_state != "visible":
                continue
            grid: Grid = []
            for values in sheet.iter_rows(min_row=1, min_col=1, values_only=True):
                total += 1
                if total > max_rows:
                    raise IngestError("too_large")
                grid.append(["" if v is None else str(v) for v in values])
            grids.append((sheet.title, grid))
    finally:
        workbook.close()
    return grids


def csv_grid(data: bytes, *, max_rows: int) -> Grid:
    text = _decode_text(data)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    grid: Grid = []
    for row in csv.reader(io.StringIO(text), dialect):
        grid.append(row)
        if len(grid) > max_rows:
            raise IngestError("too_large")
    return grid


# --- DOCX ---------------------------------------------------------------------

_HEADING_STYLES = ("title", "heading")


def docx_parts(data: bytes) -> tuple[list[Grid], list[tuple[int, str, bool]]]:
    """Tables as grids, and the body paragraphs as (index, text, is_heading)."""
    try:
        document = load_docx(io.BytesIO(data))
    except Exception:
        raise IngestError("corrupt") from None
    tables: list[Grid] = []
    paragraphs: list[tuple[int, str, bool]] = []
    index = 0
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:tbl"):
            table = Table(child, document)
            grid: Grid = []
            for row in table.rows:
                seen: set[int] = set()
                cells = []
                for cell in row.cells:
                    if id(cell._tc) in seen:  # merged cells repeat
                        continue
                    seen.add(id(cell._tc))
                    cells.append(clean(cell.text))
                grid.append(cells)
            tables.append(grid)
        elif child.tag == qn("w:p"):
            paragraph = Paragraph(child, document)
            style = (paragraph.style.name if paragraph.style is not None else "") or ""
            text = clean(paragraph.text)
            if text:
                paragraphs.append((index, text, style.lower().startswith(_HEADING_STYLES)))
            index += 1
    return tables, paragraphs


def docx_paragraph_questions(paragraphs: list[tuple[int, str, bool]]) -> list[ExtractedQuestion]:
    """Questions written as body paragraphs (numbered lists, "Describe ..." lines)."""
    questions: list[ExtractedQuestion] = []
    section: str | None = None
    for index, text, is_heading in paragraphs:
        if is_heading:
            section = text[:200]
            continue
        ref, rest = split_ref(text)
        if is_question_sentence(rest):
            questions.append(
                ExtractedQuestion(text=rest, ref=ref, section=section, locator={"paragraph": index})
            )
    return questions


# --- PDF ------------------------------------------------------------------------


def pdf_text_lines(data: bytes, *, max_pages: int) -> list[Line]:
    return [
        Line(text=text, page=page, size=size, bold=bold)
        for page, text, size, bold in read_lines(data, max_pages=max_pages)
    ]


# --- XML ---------------------------------------------------------------------------

_XML_TEXT_TAGS = {"question", "text", "prompt", "item", "requirement", "q"}
_XML_SECTION_TAGS = {"section", "domain", "category", "group", "part"}
_XML_REF_ATTRS = ("id", "ref", "number", "num", "code")


def xml_questions(data: bytes, *, max_questions: int) -> list[ExtractedQuestion]:
    """Elements whose text is a question. External entities and DTDs are refused."""
    try:
        root = ElementTree.fromstring(_decode_text(data), forbid_dtd=True)
    except (ElementTree.ParseError, DefusedXmlException):
        raise IngestError("corrupt") from None
    questions: list[ExtractedQuestion] = []

    def local(tag: Any) -> str:
        return str(tag).rsplit("}", 1)[-1].lower()

    def walk(element: Any, section: str | None, path: str) -> None:
        tag = local(element.tag)
        if tag in _XML_SECTION_TAGS:
            title = element.get("name") or element.get("title")
            section = clean(title) if title else section
        text = clean(element.text or "")
        is_question = text and (tag in _XML_TEXT_TAGS or looks_like_question(text))
        if is_question and len(text.split()) >= 3:
            ref = next((element.get(a) for a in _XML_REF_ATTRS if element.get(a)), None)
            parsed_ref, text = split_ref(text)
            questions.append(
                ExtractedQuestion(
                    text=text,
                    ref=(ref or parsed_ref),
                    section=section,
                    locator={"xpath": path},
                )
            )
            if len(questions) > max_questions:
                raise IngestError("too_large")
        counts: dict[str, int] = {}
        for child in element:
            name = local(child.tag)
            counts[name] = counts.get(name, 0) + 1
            walk(child, section, f"{path}/{name}[{counts[name]}]")

    walk(root, None, f"/{local(root.tag)}")
    return questions

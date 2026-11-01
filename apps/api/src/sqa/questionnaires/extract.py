"""Pick the right reader for a questionnaire and return its questions."""

from collections.abc import Callable
from typing import Any, Literal, Protocol

from sqa.core.config import Settings
from sqa.ingestion.types import IngestError
from sqa.models import QuestionnaireKind
from sqa.questionnaires import readers
from sqa.questionnaires.lines import LineClassifier, extract_from_lines
from sqa.questionnaires.ocr import ocr_document
from sqa.questionnaires.tabular import (
    Grid,
    LocatorFn,
    SheetMapping,
    detect_mapping,
    extract_rows,
    preview,
    sheet_locator,
)
from sqa.questionnaires.types import ExtractedQuestion, Extraction

OcrEngineName = Literal["local", "claude", "none"]


class VisionExtractor(Protocol):
    name: str

    async def extract(self, data: bytes, media_type: str) -> list[ExtractedQuestion]: ...


async def extract_questionnaire(
    kind: QuestionnaireKind,
    data: bytes,
    content_type: str,
    settings: Settings,
    *,
    user_mapping: dict[str, Any] | None = None,
    classifier: LineClassifier | None = None,
    vision: VisionExtractor | None = None,
) -> Extraction:
    if kind in (QuestionnaireKind.XLSX, QuestionnaireKind.CSV):
        if kind is QuestionnaireKind.XLSX:
            grids = readers.xlsx_grids(data, max_rows=settings.max_spreadsheet_rows)
        else:
            grids = [("CSV", readers.csv_grid(data, max_rows=settings.max_spreadsheet_rows))]
        return _from_grids(grids, user_mapping, sheet_locator)

    if kind is QuestionnaireKind.DOCX:
        tables, paragraphs = readers.docx_parts(data)
        named = [(f"Table {i + 1}", grid) for i, grid in enumerate(tables)]
        tabular = _from_grids(named, user_mapping, _table_locator, allow_empty=True)
        questions = tabular.questions + readers.docx_paragraph_questions(paragraphs)
        return Extraction(
            questions=questions,
            extractor="docx",
            mapping=tabular.mapping,
            preview=tabular.preview,
            needs_mapping=not questions and bool(tables),
        )

    if kind is QuestionnaireKind.XML:
        found = readers.xml_questions(data, max_questions=settings.max_questionnaire_questions)
        return Extraction(questions=found, extractor="xml")

    # PDF with a text layer: read the text. Scans and images: OCR (or Claude, if chosen).
    if kind is QuestionnaireKind.PDF:
        lines = readers.pdf_text_lines(data, max_pages=settings.max_document_pages)
        if sum(len(line.text) for line in lines) >= 40:
            return Extraction(questions=extract_from_lines(lines, classifier), extractor="pdf-text")
    return await _from_scan(kind, data, content_type, settings, classifier, vision)


async def _from_scan(
    kind: QuestionnaireKind,
    data: bytes,
    content_type: str,
    settings: Settings,
    classifier: LineClassifier | None,
    vision: VisionExtractor | None,
) -> Extraction:
    engine: OcrEngineName = settings.questionnaire_ocr
    if engine == "claude":
        if vision is None:
            raise IngestError("vision_unavailable")
        return Extraction(questions=await vision.extract(data, content_type), extractor=vision.name)
    if engine == "none":
        raise IngestError("no_text")
    lines = await ocr_document(
        data, is_pdf=kind is QuestionnaireKind.PDF, max_pages=settings.max_ocr_pages
    )
    if not lines:
        raise IngestError("no_text")
    return Extraction(questions=extract_from_lines(lines, classifier), extractor="ocr-local")


def _table_locator(table: str) -> LocatorFn:
    """DOCX table rows: table number, row index and answer column."""
    number = int(table.split()[-1])

    def locator(row_index: int, mapping: SheetMapping) -> dict[str, Any]:
        return {"table": number, "row": row_index, "answer_col": mapping.answer_col}

    return locator


def _from_grids(
    grids: list[tuple[str, Grid]],
    user_mapping: dict[str, Any] | None,
    locator_factory: Callable[[str], LocatorFn],
    *,
    allow_empty: bool = False,
) -> Extraction:
    """Use the user's mapping when given; otherwise detect a header per sheet."""
    if user_mapping is not None:
        mappings = [SheetMapping.from_dict(m) for m in user_mapping.get("sheets", [])]
    else:
        mappings = [m for name, grid in grids if (m := detect_mapping(name, grid))]
    by_name = dict(grids)
    questions: list[ExtractedQuestion] = []
    for mapping in mappings:
        grid = by_name.get(mapping.sheet)
        if grid is None or (mapping.header_row or 0) >= len(grid):
            raise IngestError("bad_mapping")
        questions.extend(extract_rows(grid, mapping, locator_factory(mapping.sheet)))
    previews = {"sheets": [preview(name, grid) for name, grid in grids if grid]}
    return Extraction(
        questions=questions,
        extractor="spreadsheet",
        mapping={"sheets": [m.to_dict() for m in mappings]},
        preview=previews,
        needs_mapping=not questions and not allow_empty,
    )

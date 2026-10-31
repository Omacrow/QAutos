"""XLSX extraction: one block per row, cited as sheet + row number.

Security teams keep past questionnaire answers in spreadsheets, so a row such
as "Question: Do you encrypt backups? | Answer: Yes, AES-256" is the unit of
evidence. Each value is labelled with its column header so a row reads on its
own once it is split away from the header row.
"""

import io
from datetime import date, datetime
from typing import Any

from openpyxl import load_workbook

from sqa.ingestion.types import Block, IngestError, ParsedDocument

HEADER_SCAN_ROWS = 20
MAX_CELL_CHARS = 4000


def parse_xlsx(data: bytes, *, max_rows: int) -> ParsedDocument:
    try:
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception:
        raise IngestError("corrupt") from None

    blocks: list[Block] = []
    total_rows = 0
    try:
        for sheet in workbook.worksheets:
            if sheet.sheet_state != "visible":
                continue
            header: list[str] | None = None
            for row_no, values in enumerate(sheet.iter_rows(values_only=True), start=1):
                total_rows += 1
                if total_rows > max_rows:
                    raise IngestError("too_large")
                cells = [_cell_text(v) for v in values]
                filled = [c for c in cells if c]
                if not filled:
                    continue
                if header is None and row_no <= HEADER_SCAN_ROWS and _looks_like_header(cells):
                    header = cells
                    continue
                blocks.append(
                    Block(
                        text=_row_text(cells, header),
                        sheet=sheet.title,
                        row=row_no,
                        heading_path=(sheet.title,),
                    )
                )
    finally:
        workbook.close()
    if not blocks:
        raise IngestError("no_text")
    return ParsedDocument(blocks=blocks, parser="openpyxl")


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return " ".join(str(value).split())[:MAX_CELL_CHARS]


def _looks_like_header(cells: list[str]) -> bool:
    """At least two short, non-numeric labels: "Question", "Answer", "Control ID"."""
    labels = [c for c in cells if c]
    return len(labels) >= 2 and all(
        len(c) <= 60 and not c.replace(".", "", 1).isdigit() for c in labels
    )


def _row_text(cells: list[str], header: list[str] | None) -> str:
    if header is None:
        return " | ".join(c for c in cells if c)
    parts = []
    for i, value in enumerate(cells):
        if not value:
            continue
        label = header[i] if i < len(header) and header[i] else None
        parts.append(f"{label}: {value}" if label else value)
    return " | ".join(parts)

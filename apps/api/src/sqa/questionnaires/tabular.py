"""Questions from grids: spreadsheet sheets, CSV files and DOCX tables.

Most questionnaires (CAIQ, SIG, HECVAT, vendor custom) are spreadsheets with a
header row naming the question and answer columns. We look for that header in
the first rows, classify its columns, then read one question per row. Rows
that only carry a domain name ("Audit & Assurance") become the section for
the questions below them.

When no header names a question column, the user picks the columns in the UI
(`needs_mapping`); their choice comes back here as a `SheetMapping`.
"""

from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from sqa.questionnaires.heuristics import clean, column_letter, looks_like_question, split_ref
from sqa.questionnaires.types import ExtractedQuestion

HEADER_SCAN_ROWS = 30
MAX_HEADER_CELL_CHARS = 60
PREVIEW_ROWS = 12
PREVIEW_COLS = 12

Grid = list[list[str]]


@dataclass(frozen=True, slots=True)
class SheetMapping:
    sheet: str
    header_row: int | None  # 0-based index into the grid; None: no header row
    question_col: int
    answer_col: int | None = None
    ref_col: int | None = None
    comment_col: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SheetMapping":
        return cls(
            sheet=str(data["sheet"]),
            header_row=_opt_int(data.get("header_row")),
            question_col=int(data["question_col"]),
            answer_col=_opt_int(data.get("answer_col")),
            ref_col=_opt_int(data.get("ref_col")),
            comment_col=_opt_int(data.get("comment_col")),
        )


def _opt_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _role_scores(cell: str) -> dict[str, int]:
    """How strongly a header cell suggests each column role."""
    text = clean(cell).lower()
    if not text or len(text) > MAX_HEADER_CELL_CHARS:
        return {}
    scores: dict[str, int] = {}
    words = set(text.replace("#", " # ").replace(".", " ").split())
    id_like = bool(words & {"id", "#", "ref", "no", "number", "num"})
    if "question" in text and not id_like:
        scores["question"] = 3
    elif any(k in text for k in ("requirement", "query", "criteria", "criterion")):
        scores["question"] = 2
    elif any(k in text for k in ("description", "item", "control")):
        scores["question"] = 1
    if (
        (any(k in text for k in ("answer", "response", "reply")) and "question" not in text)
        or text in {"yes/no", "y/n", "yes / no", "y / n"}
        or "yes/no" in text
    ):
        scores["answer"] = 3
    elif any(k in text for k in ("compliant", "compliance", "status", "selection")):
        scores["answer"] = 1
    if text in {"#", "id", "no", "no.", "ref", "ref.", "number", "item #", "q#", "q #"} or (
        words & {"id", "#", "ref", "ref."} and len(words) <= 3
    ):
        scores["ref"] = 2
    if any(
        k in text
        for k in (
            "comment",
            "note",
            "explanation",
            "evidence",
            "justification",
            "remark",
            "additional",
        )
    ):
        scores["comment"] = 2
    return scores


def detect_mapping(sheet: str, grid: Grid) -> SheetMapping | None:
    """Find the header row and assign question/answer/ref/comment columns."""
    best: tuple[float, SheetMapping] | None = None
    for row_index, row in enumerate(grid[:HEADER_SCAN_ROWS]):
        scored = [(col, _role_scores(cell)) for col, cell in enumerate(row)]
        roles: dict[str, int] = {}
        taken: set[int] = set()
        for role in ("question", "answer", "ref", "comment"):
            candidates = [
                (score[role], -col, col)
                for col, score in scored
                if role in score and col not in taken
            ]
            if candidates:
                _, _, col = max(candidates)
                roles[role] = col
                taken.add(col)
        # A header labels several columns; one sentence mentioning "question" isn't one.
        if "question" not in roles or sum(1 for cell in row if clean(cell)) < 2:
            continue
        question_score = dict(scored)[roles["question"]]["question"]
        total = question_score + (2 if "answer" in roles else 0) + (0.5 if "ref" in roles else 0)
        if total < 3:  # a lone weak match ("Description") isn't a header
            continue
        mapping = SheetMapping(
            sheet=sheet,
            header_row=row_index,
            question_col=roles["question"],
            answer_col=roles.get("answer"),
            ref_col=roles.get("ref"),
            comment_col=roles.get("comment"),
        )
        if best is None or total > best[0]:
            best = (total, mapping)
    return best[1] if best else None


def extract_rows(
    grid: Grid,
    mapping: SheetMapping,
    locator_for: "LocatorFn",
) -> list[ExtractedQuestion]:
    """One question per row below the header; label rows set the section."""
    questions: list[ExtractedQuestion] = []
    section: str | None = None
    first = 0 if mapping.header_row is None else mapping.header_row + 1
    for row_index in range(first, len(grid)):
        row = grid[row_index]
        filled = [(col, clean(value)) for col, value in enumerate(row) if clean(value)]
        if not filled:
            continue
        text = _cell(row, mapping.question_col)
        ref = _cell(row, mapping.ref_col) if mapping.ref_col is not None else ""

        # A row with one filled cell outside the question column is a section label.
        if len(filled) == 1 and filled[0][0] != mapping.question_col:
            section = filled[0][1][:200]
            continue
        if not text:
            continue
        if _is_section_label(text, ref, mapping):
            section = text[:200]
            continue
        if len(text) < 6:
            continue
        if not ref:
            parsed_ref, text = split_ref(text)
            ref = parsed_ref or ""
        questions.append(
            ExtractedQuestion(
                text=text,
                ref=ref[:64] or None,
                section=section,
                locator=locator_for(row_index, mapping),
            )
        )
    return questions


LocatorFn = Callable[[int, SheetMapping], dict[str, Any]]


def _is_section_label(text: str, ref: str, mapping: SheetMapping) -> bool:
    """Only when clearly a label: losing a real question is worse than keeping a heading."""
    if looks_like_question(text):
        return False
    if text.endswith(":") or (text.isupper() and len(text) <= 80):
        return True
    return mapping.ref_col is not None and not ref and len(text) <= 80


def _cell(row: list[str], col: int | None) -> str:
    if col is None or col >= len(row):
        return ""
    return clean(row[col])


def sheet_locator(sheet: str, first_row: int = 1) -> LocatorFn:
    """Locator for spreadsheet rows: A1 cells, so export can write the answer back."""

    def locator(row_index: int, mapping: SheetMapping) -> dict[str, Any]:
        row_number = row_index + first_row
        return {
            "sheet": sheet,
            "row": row_number,
            "question_cell": f"{column_letter(mapping.question_col)}{row_number}",
            "answer_cell": (
                f"{column_letter(mapping.answer_col)}{row_number}"
                if mapping.answer_col is not None
                else None
            ),
        }

    return locator


def preview(sheet: str, grid: Grid) -> dict[str, Any]:
    return {
        "sheet": sheet,
        "row_count": len(grid),
        "rows": [[clean(cell)[:120] for cell in row[:PREVIEW_COLS]] for row in grid[:PREVIEW_ROWS]],
    }

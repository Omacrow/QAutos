"""PDF text extraction with page numbers and section headings.

Headings come from the PDF outline (bookmarks) when it has one: authors put
them there on purpose, so they beat any guess. Otherwise a line counts as a
heading when its font is clearly larger than the body text, or bold and short.
Running headers and footers ("Confidential", "Page 3 of 12") repeat on most
pages and would pollute every chunk, so they are dropped.
"""

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

import pymupdf

from sqa.ingestion.types import Block, IngestError, ParsedDocument

MAX_HEADING_CHARS = 120
MAX_HEADING_LEVELS = 3
_BOLD_FLAG = 16
# Top/bottom fraction of the page where running headers/footers live.
_MARGIN_BAND = 0.08


@dataclass(slots=True)
class _Line:
    text: str
    size: float
    bold: bool
    y0: float
    y1: float


def parse_pdf(data: bytes, *, max_pages: int, parser: str = "pymupdf") -> ParsedDocument:
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        raise IngestError("corrupt") from None
    with doc:
        if doc.needs_pass:
            raise IngestError("encrypted")
        if doc.page_count > max_pages:
            raise IngestError("too_many_pages")

        pages = [_page_blocks(doc[i]) for i in range(doc.page_count)]
        heights = [doc[i].rect.height for i in range(doc.page_count)]
        toc = [(lvl, title.strip(), page) for lvl, title, page in doc.get_toc(simple=True)]

    repeated = _running_lines(pages, heights)
    empty_pages = [i + 1 for i, blocks in enumerate(pages) if not any(blocks)]
    if len(empty_pages) == len(pages):
        raise IngestError("no_text")

    if len(toc) >= 2:
        blocks = _blocks_from_toc(pages, repeated, toc)
    else:
        blocks = _blocks_from_fonts(pages, repeated)
    return ParsedDocument(
        blocks=blocks, parser=parser, page_count=len(pages), empty_pages=empty_pages
    )


def _page_blocks(page: Any) -> list[list[_Line]]:
    """Text blocks (roughly paragraphs) of one page, each a list of lines."""
    out: list[list[_Line]] = []
    for block in page.get_text("dict", sort=True)["blocks"]:
        lines: list[_Line] = []
        for line in block.get("lines", []):
            spans = [s for s in line["spans"] if s["text"].strip()]
            if not spans:
                continue
            text = " ".join(s["text"].strip() for s in spans)
            lines.append(
                _Line(
                    text=_clean(text),
                    size=round(max(s["size"] for s in spans) * 2) / 2,
                    bold=all(s["flags"] & _BOLD_FLAG for s in spans),
                    y0=line["bbox"][1],
                    y1=line["bbox"][3],
                )
            )
        if lines:
            out.append(lines)
    return out


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _signature(text: str) -> str:
    """Normalize page numbers away so "Page 3" and "Page 4" match."""
    return re.sub(r"\d+", "#", text.lower())


def _running_lines(pages: list[list[list[_Line]]], heights: list[float]) -> set[str]:
    if len(pages) < 3:
        return set()
    counts: Counter[str] = Counter()
    for blocks, height in zip(pages, heights, strict=True):
        seen = {
            _signature(line.text)
            for block in blocks
            for line in block
            if line.y1 <= height * _MARGIN_BAND or line.y0 >= height * (1 - _MARGIN_BAND)
        }
        counts.update(seen)
    threshold = max(3, len(pages) // 2)
    return {sig for sig, n in counts.items() if n >= threshold}


def _body_size(pages: list[list[list[_Line]]]) -> float:
    weights: Counter[float] = Counter()
    for blocks in pages:
        for block in blocks:
            for line in block:
                weights[line.size] += len(line.text)
    return weights.most_common(1)[0][0] if weights else 0.0


def _blocks_from_fonts(pages: list[list[list[_Line]]], repeated: set[str]) -> list[Block]:
    body = _body_size(pages)

    def heading_size(line: _Line) -> float | None:
        if len(line.text) > MAX_HEADING_CHARS or not re.search(r"[A-Za-z]", line.text):
            return None
        if line.size >= body + 1.5:
            return line.size
        if line.bold and line.size >= body and len(line.text) <= 80 and line.text[-1] != ".":
            return line.size - 0.25  # bold body-size headings rank below larger ones
        return None

    sizes = sorted(
        {
            size
            for blocks in pages
            for block in blocks
            for line in block
            if (size := heading_size(line)) is not None
        },
        reverse=True,
    )
    level_of = {size: min(i + 1, MAX_HEADING_LEVELS) for i, size in enumerate(sizes)}

    path: list[tuple[int, str]] = []
    out: list[Block] = []
    for page_no, blocks in enumerate(pages, start=1):
        for block in blocks:
            buffer: list[str] = []
            previous_level: int | None = None  # level of the previous line if it was a heading
            for line in block:
                if _signature(line.text) in repeated:
                    continue
                size = heading_size(line)
                if size is None:
                    buffer.append(line.text)
                    previous_level = None
                    continue
                level = level_of[size]
                if previous_level == level and path:
                    # A heading wrapped onto a second line: join it.
                    path[-1] = (level, f"{path[-1][1]} {line.text}")
                    continue
                _flush(out, buffer, page_no, path)
                path = [p for p in path if p[0] < level] + [(level, line.text)]
                previous_level = level
            _flush(out, buffer, page_no, path)
    return out


def _blocks_from_toc(
    pages: list[list[list[_Line]]],
    repeated: set[str],
    toc: list[tuple[int, str, int]],
) -> list[Block]:
    by_page: dict[int, list[tuple[int, str]]] = {}
    for level, title, page in toc:
        if title and page >= 1:
            by_page.setdefault(page, []).append((min(level, MAX_HEADING_LEVELS), title))

    path: list[tuple[int, str]] = []
    out: list[Block] = []
    for page_no, blocks in enumerate(pages, start=1):
        pending = list(by_page.get(page_no, []))
        for block in blocks:
            buffer: list[str] = []
            for line in block:
                if _signature(line.text) in repeated:
                    continue
                match = next(
                    (p for p in pending if _clean(p[1]).lower() == line.text.lower()), None
                )
                if match is None:
                    buffer.append(line.text)
                    continue
                _flush(out, buffer, page_no, path)
                # Entries before the matched one start on this page too; apply in order.
                for entry in pending[: pending.index(match) + 1]:
                    path = [p for p in path if p[0] < entry[0]] + [entry]
                pending = pending[pending.index(match) + 1 :]
            _flush(out, buffer, page_no, path)
        # Bookmarks whose title text we couldn't find still start a section.
        for entry in pending:
            path = [p for p in path if p[0] < entry[0]] + [entry]
    return out


def _flush(out: list[Block], buffer: list[str], page: int, path: list[tuple[int, str]]) -> None:
    text = _join_lines(buffer)
    buffer.clear()
    if text:
        out.append(Block(text=text, page=page, heading_path=tuple(t for _, t in path)))


def _join_lines(lines: list[str]) -> str:
    """Join wrapped lines, repairing words hyphenated across a line break."""
    text = ""
    for line in lines:
        if text.endswith("-") and line[:1].islower():
            text = text[:-1] + line
        else:
            text = f"{text} {line}" if text else line
    return text.strip()

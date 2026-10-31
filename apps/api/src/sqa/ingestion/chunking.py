"""Page-aware chunking.

Rules, in order of importance:
1. A chunk never crosses a section (heading path) or sheet boundary, so its
   heading is always accurate and a citation never points at the wrong section.
2. A chunk records the page range (or row range) it covers.
3. Chunks aim for `target_chars` (~300-400 tokens): small enough that the
   evidence check in Phase 2 can judge a passage, large enough to hold a whole
   policy statement.
   Spreadsheet chunks are smaller (a few rows), so a citation names the row.
4. Prose chunks overlap by the trailing sentence(s) of the previous chunk, so
   a statement split across a boundary is still found whole. Spreadsheet rows
   are self-contained and never overlap.
"""

import re
from dataclasses import dataclass
from itertools import groupby

from sqa.ingestion.types import Block

TARGET_CHARS = 1500
SHEET_TARGET_CHARS = 500
MAX_CHARS = 2000
OVERLAP_CHARS = 250
MIN_CHARS = 200

_SENTENCE_END = re.compile(r"(?<=[.!?;:])\s+(?=[\"'(\[]?[A-Z0-9])")


@dataclass(frozen=True, slots=True)
class Chunk:
    ordinal: int
    text: str
    heading_path: tuple[str, ...]
    page_start: int | None = None
    page_end: int | None = None
    sheet: str | None = None
    row_start: int | None = None
    row_end: int | None = None

    @property
    def heading(self) -> str | None:
        return " > ".join(self.heading_path) or None


@dataclass(slots=True)
class _Piece:
    text: str
    page: int | None
    row: int | None


def chunk_blocks(
    blocks: list[Block],
    *,
    target_chars: int = TARGET_CHARS,
    sheet_target_chars: int = SHEET_TARGET_CHARS,
    max_chars: int = MAX_CHARS,
    overlap_chars: int = OVERLAP_CHARS,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for (heading_path, sheet), group in groupby(blocks, key=lambda b: (b.heading_path, b.sheet)):
        target = min(sheet_target_chars if sheet else target_chars, max_chars)
        pieces = [
            _Piece(text, block.page, block.row)
            for block in group
            for text in _split_long(block.text, target)
        ]
        windows = _windows(pieces, target, max_chars, 0 if sheet else overlap_chars)
        for window in windows:
            pages = [p.page for p in window if p.page is not None]
            rows = [p.row for p in window if p.row is not None]
            chunks.append(
                Chunk(
                    ordinal=len(chunks),
                    text="\n".join(p.text for p in window),
                    heading_path=heading_path,
                    page_start=min(pages) if pages else None,
                    page_end=max(pages) if pages else None,
                    sheet=sheet,
                    row_start=min(rows) if rows else None,
                    row_end=max(rows) if rows else None,
                )
            )
    return chunks


def _windows(pieces: list[_Piece], target: int, maximum: int, overlap: int) -> list[list[_Piece]]:
    windows: list[list[_Piece]] = []
    current: list[_Piece] = []
    size = 0
    fresh = 0  # pieces in `current` not already emitted as overlap
    for piece in pieces:
        if current and fresh and size + len(piece.text) > target:
            windows.append(current)
            current = _tail(current, overlap)
            size = _size(current)
            fresh = 0
        if not fresh and size + len(piece.text) > maximum:
            current, size = [], 0  # no room for the overlap
        current.append(piece)
        size += len(piece.text) + 1
        fresh += 1
    if current and fresh:
        # Fold a short remainder into the previous window rather than emit a scrap.
        if windows and size < MIN_CHARS and _size(windows[-1]) + size <= maximum:
            windows[-1].extend(current[len(current) - fresh :])
        else:
            windows.append(current)
    return windows


def _tail(pieces: list[_Piece], overlap: int) -> list[_Piece]:
    """Trailing sentences of the last piece, up to `overlap` chars, to repeat next."""
    if overlap <= 0 or not pieces:
        return []
    last = pieces[-1]
    tail: list[str] = []
    for sentence in reversed(_sentences(last.text)):
        if sum(len(s) + 1 for s in tail) + len(sentence) > overlap:
            break
        tail.insert(0, sentence)
    if not tail:
        return []
    return [_Piece(" ".join(tail), last.page, last.row)]


def _size(pieces: list[_Piece]) -> int:
    return sum(len(p.text) + 1 for p in pieces)


def _sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_END.split(text) if s.strip()]


def _split_long(text: str, max_chars: int) -> list[str]:
    """Split text longer than `max_chars` at sentence ends, then at spaces.

    Called with the target size, so a split block fills whole chunks.
    """
    if len(text) <= max_chars:
        return [text]
    parts: list[str] = []
    current = ""
    for sentence in _sentences(text):
        while len(sentence) > max_chars:
            cut = sentence.rfind(" ", 0, max_chars)
            cut = cut if cut > max_chars // 2 else max_chars
            if current:
                parts.append(current)
                current = ""
            parts.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if current and len(current) + 1 + len(sentence) > max_chars:
            parts.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}" if current else sentence
    if current:
        parts.append(current)
    return parts

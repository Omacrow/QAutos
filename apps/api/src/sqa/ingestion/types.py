from dataclasses import dataclass, field


class IngestError(Exception):
    """A document we can't process. `code` is shown to users; never the message."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class Block:
    """One paragraph, table row or spreadsheet row, with where it came from."""

    text: str
    page: int | None = None
    heading_path: tuple[str, ...] = ()
    sheet: str | None = None
    row: int | None = None


@dataclass(slots=True)
class ParsedDocument:
    blocks: list[Block]
    parser: str
    page_count: int | None = None
    # Pages with no extractable text (likely scanned). OCR is out of scope for now.
    empty_pages: list[int] = field(default_factory=list)

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ExtractedQuestion:
    text: str
    ref: str | None = None
    section: str | None = None
    locator: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Extraction:
    questions: list[ExtractedQuestion]
    extractor: str
    # Column mapping used for spreadsheets / tables (see tabular.SheetMapping).
    mapping: dict[str, Any] | None = None
    # Sheet previews, so the user can pick columns when detection fails.
    preview: dict[str, Any] | None = None
    needs_mapping: bool = False


class TransientExtractionError(Exception):
    """Rate limit or provider outage: the job is retried later."""

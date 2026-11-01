"""Optional engine: Claude reads a scanned questionnaire and lists its questions.

Off by default (the local OCR engine is the default). Enabled with
QUESTIONNAIRE_OCR=claude and ANTHROPIC_API_KEY. Uses structured outputs, so the
response is JSON matching QUESTIONS_SCHEMA.
"""

import base64
import json
from typing import Any, cast

import anthropic
from anthropic.types.beta import BetaMessageParam

from sqa.ingestion.types import IngestError
from sqa.questionnaires.heuristics import clean
from sqa.questionnaires.types import ExtractedQuestion, TransientExtractionError

MAX_PDF_PAGES = 100
MAX_OUTPUT_TOKENS = 64000

PROMPT = """This is a security or compliance questionnaire sent to a vendor.

List every question or requirement the vendor is expected to answer, in document order.
- Copy each question's wording exactly; join lines that wrap.
- `ref`: the question's number or control id as printed (e.g. "3.2", "IAM-14.1"), else null.
- `section`: the heading the question sits under, else null.
- `page`: the 1-based page number, else null for single images.
Do not include instructions, headings, answer options or example answers as questions."""

QUESTIONS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ref": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "section": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "text": {"type": "string"},
                    "page": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
                },
                "required": ["ref", "section", "text", "page"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["questions"],
    "additionalProperties": False,
}


def _source_block(data: bytes, media_type: str) -> dict[str, Any]:
    encoded = base64.standard_b64encode(data).decode("ascii")
    block_type = "document" if media_type == "application/pdf" else "image"
    return {
        "type": block_type,
        "source": {"type": "base64", "media_type": media_type, "data": encoded},
    }


class ClaudeVisionExtractor:
    name = "claude-vision"

    def __init__(self, client: anthropic.AsyncAnthropic, *, model: str) -> None:
        self._client = client
        self._model = model

    async def extract(self, data: bytes, media_type: str) -> list[ExtractedQuestion]:
        try:
            async with self._client.beta.messages.stream(
                model=self._model,
                max_tokens=MAX_OUTPUT_TOKENS,
                # Re-run on Anthropic's recommended model if a safety classifier declines.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                output_config={
                    "effort": "medium",
                    "format": {"type": "json_schema", "schema": QUESTIONS_SCHEMA},
                },
                messages=cast(
                    "list[BetaMessageParam]",
                    [
                        {
                            "role": "user",
                            "content": [
                                _source_block(data, media_type),
                                {"type": "text", "text": PROMPT},
                            ],
                        }
                    ],
                ),
            ) as stream:
                message = await stream.get_final_message()
        except (
            anthropic.RateLimitError,
            anthropic.APIConnectionError,
            anthropic.InternalServerError,
        ):
            raise TransientExtractionError("claude") from None
        except anthropic.APIStatusError:
            # Never surface the error body: it can echo document content.
            raise IngestError("vision_failed") from None

        if message.stop_reason == "refusal":
            raise IngestError("extraction_refused")
        if message.stop_reason == "max_tokens":
            raise IngestError("too_large")
        text = next((b.text for b in message.content if b.type == "text"), "")
        try:
            items = json.loads(text)["questions"]
        except (json.JSONDecodeError, KeyError, TypeError):
            raise IngestError("vision_failed") from None
        return [
            ExtractedQuestion(
                text=clean(item["text"]),
                ref=(clean(item["ref"])[:64] or None) if item.get("ref") else None,
                section=clean(item["section"])[:200] if item.get("section") else None,
                locator={"page": item["page"]} if item.get("page") else {},
            )
            for item in items
            if clean(item.get("text") or "")
        ]

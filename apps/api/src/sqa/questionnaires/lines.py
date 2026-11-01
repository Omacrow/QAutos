"""Questions from lines of text: PDF text layers and OCR output.

Each line is labelled by a `LineClassifier`: QUESTION (starts a question),
SECTION (a heading), ANSWER (an answer slot such as "Response: ____") or OTHER.
A question continues onto following OTHER lines until it ends with "?" or "."
or the next labelled line starts.

`HeuristicLineClassifier` is the rule-based baseline. A trained classifier
(Phase 2 ML work) implements the same interface and is compared against it on
the labelled test corpus.
"""

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from sqa.questionnaires.heuristics import (
    clean,
    is_answer_label,
    is_question_sentence,
    split_ref,
)
from sqa.questionnaires.types import ExtractedQuestion

_SECTION_WORDS = ("section", "part", "domain", "category", "chapter")


class LineLabel(StrEnum):
    QUESTION = "question"
    SECTION = "section"
    ANSWER = "answer"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class Line:
    text: str
    page: int
    size: float  # font size (PDF) or box height (OCR)
    bold: bool = False


class LineClassifier(Protocol):
    name: str

    def classify(self, line: Line, body_size: float) -> LineLabel: ...


class HeuristicLineClassifier:
    name = "heuristic"

    def classify(self, line: Line, body_size: float) -> LineLabel:
        text = clean(line.text)
        if not text:
            return LineLabel.OTHER
        if is_answer_label(text):
            return LineLabel.ANSWER
        ref, rest = split_ref(text)
        # Numbered line: a question if it reads like one. OCR may lowercase the first
        # letter ("ls ..."), so a question mark alone is enough.
        if ref and (
            "?" in rest or (_starts_well(rest) and is_question_sentence(rest, min_words=3))
        ):
            return LineLabel.QUESTION
        # A numbered full sentence in a questionnaire is a question even when its
        # first line has no "?" yet ("3.4 Within what timeframe will ... <wraps>").
        if ref and _starts_well(rest) and len(rest.split()) >= 6:
            return LineLabel.QUESTION
        lower = text.lower()
        if lower.startswith(_SECTION_WORDS) and "?" not in text and len(text) <= 100:
            return LineLabel.SECTION
        if is_question_sentence(text):
            return LineLabel.QUESTION
        larger = body_size > 0 and line.size >= body_size * 1.15
        if (larger or line.bold or text.isupper()) and "?" not in text and len(text) <= 90:
            return LineLabel.SECTION
        return LineLabel.OTHER


def _starts_well(text: str) -> bool:
    return text[:1].isupper() or text[:1].isdigit()


def body_size(lines: list[Line]) -> float:
    weights: Counter[float] = Counter()
    for line in lines:
        weights[round(line.size * 2) / 2] += len(line.text)
    return weights.most_common(1)[0][0] if weights else 0.0


def extract_from_lines(
    lines: list[Line], classifier: LineClassifier | None = None
) -> list[ExtractedQuestion]:
    classifier = classifier or HeuristicLineClassifier()
    body = body_size(lines)
    questions: list[ExtractedQuestion] = []
    section: str | None = None
    current: ExtractedQuestion | None = None

    def close() -> None:
        nonlocal current
        if current is not None and len(current.text) >= 10:
            questions.append(current)
        current = None

    for line in lines:
        text = clean(line.text)
        if not text:
            continue
        label = classifier.classify(line, body)
        if label is LineLabel.QUESTION:
            close()
            ref, rest = split_ref(text)
            current = ExtractedQuestion(
                text=rest, ref=ref, section=section, locator={"page": line.page}
            )
        elif label is LineLabel.SECTION:
            close()
            section = text.rstrip(":")[:200]
        elif label is LineLabel.ANSWER:
            close()
        elif current is not None and not current.text.endswith(("?", ".")):
            current.text = f"{current.text} {text}"  # wrapped question line
        else:
            close()
    close()
    return questions

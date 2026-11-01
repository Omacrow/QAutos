"""Extraction accuracy against an answer key.

precision: share of extracted items that are real questions.
recall: share of real questions that were extracted.
Matching is fuzzy (normalized text, similarity >= 0.9) so OCR's occasional
character slip doesn't count as a miss, and each expected question matches once.
"""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

MATCH_THRESHOLD = 0.9


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


@dataclass(frozen=True, slots=True)
class ExtractionScore:
    expected: int
    extracted: int
    matched: int
    missed: list[str]
    spurious: list[str]

    @property
    def precision(self) -> float:
        return (
            self.matched / self.extracted if self.extracted else (1.0 if not self.expected else 0.0)
        )

    @property
    def recall(self) -> float:
        return self.matched / self.expected if self.expected else 1.0


def score(expected: list[str], extracted: list[str]) -> ExtractionScore:
    remaining = {i: normalize(q) for i, q in enumerate(expected)}
    spurious: list[str] = []
    matched = 0
    for text in extracted:
        candidate = normalize(text)
        best, best_ratio = None, 0.0
        for i, target in remaining.items():
            ratio = SequenceMatcher(None, candidate, target).ratio()
            if ratio > best_ratio:
                best, best_ratio = i, ratio
        if best is not None and best_ratio >= MATCH_THRESHOLD:
            matched += 1
            del remaining[best]
        else:
            spurious.append(text)
    return ExtractionScore(
        expected=len(expected),
        extracted=len(extracted),
        matched=matched,
        missed=[expected[i] for i in remaining],
        spurious=spurious,
    )

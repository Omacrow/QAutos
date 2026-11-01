"""Small text rules shared by the extractors."""

import re

QUESTION_STARTERS = frozenset(
    [
        "do",
        "does",
        "did",
        "is",
        "are",
        "was",
        "were",
        "has",
        "have",
        "had",
        "can",
        "could",
        "will",
        "would",
        "should",
        "shall",
        "may",
        "must",
        "describe",
        "explain",
        "provide",
        "list",
        "please",
        "indicate",
        "specify",
        "state",
        "identify",
        "confirm",
        "outline",
        "detail",
        "attach",
        "upload",
        "define",
        "summarize",
        "submit",
        "what",
        "how",
        "when",
        "where",
        "who",
        "whom",
        "whose",
        "which",
        "why",
    ]
)

# "1.2 ...", "3) ...", "Q12. ...", "IAM-14.1 ...", "A&A-01.1 ...", "2.3.4a: ..."
_REF = re.compile(
    r"^\s*(?P<ref>(?:[A-Z][A-Z&]{0,5}[-.]?\s?)?\d{1,4}(?:[.\-]\d{1,4}){0,4}[a-z]?)"
    r"(?:[.):]\s*|\s+)(?P<rest>\S.*)$"
)
_ANSWER_LABEL = re.compile(
    r"^\s*(answer|response|vendor response|comments?|notes?|yes\s*/\s*no|y\s*/\s*n)\b\s*[:\-]?",
    re.IGNORECASE,
)


def clean(text: str) -> str:
    return " ".join(text.split())


def looks_like_question(text: str) -> bool:
    text = clean(text)
    if "?" in text:
        return True
    first = re.split(r"[\s,:;]", text.lower(), maxsplit=1)[0] if text else ""
    return first in QUESTION_STARTERS


_PLEASE_VERBS = frozenset(
    {
        "describe", "provide", "list", "explain", "confirm", "indicate",
        "attach", "specify", "identify", "outline", "detail", "state",
    }
)  # fmt: skip


def is_question_sentence(text: str, *, min_words: int = 4) -> bool:
    """A full sentence that asks something: "Do you ...?", "Describe ...", "Please provide ...".

    Stricter than `looks_like_question`: "Please complete the table below" is an
    instruction, so "please" only counts when an action verb follows.
    """
    text = clean(text)
    words = text.split()
    if len(words) < min_words or not text[:1].isupper():
        return False
    if words[0].lower().strip(",") == "please":
        return len(words) > 1 and words[1].lower().strip(",") in _PLEASE_VERBS
    return looks_like_question(text)


def split_ref(text: str) -> tuple[str | None, str]:
    """Split a leading reference ("1.2", "IAM-14.1") from the question text."""
    match = _REF.match(text)
    if not match:
        return None, clean(text)
    rest = clean(match.group("rest"))
    if len(rest) < 8:
        return None, clean(text)
    return match.group("ref").strip().rstrip("."), rest


def is_answer_label(text: str) -> bool:
    """Lines such as "Answer:", "Response: ____", "Yes / No" that follow a question."""
    stripped = clean(text)
    return bool(_ANSWER_LABEL.match(stripped)) or bool(re.fullmatch(r"[_\-.\s☐□]+", stripped))


def column_letter(index: int) -> str:
    """0 -> "A", 25 -> "Z", 26 -> "AA"."""
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters

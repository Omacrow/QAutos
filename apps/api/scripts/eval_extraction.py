"""Measure questionnaire extraction against the test corpus answer keys.

Runs offline: no database, no network (local OCR only).

Usage (from apps/api):
    uv run python scripts/make_test_corpus.py      # once
    uv run python scripts/eval_extraction.py [--corpus D:/Prods/Qautos-test] [-v]
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://unused:unused@localhost/unused")
os.environ.setdefault("CLERK_ISSUER", "https://unused.example")

from sqa.core.config import Settings
from sqa.ingestion.types import IngestError
from sqa.questionnaires.evaluate import score
from sqa.questionnaires.extract import extract_questionnaire
from sqa.questionnaires.readers import detect_kind

DEFAULT_CORPUS = Path(__file__).resolve().parents[4] / "Qautos-test"


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("-v", "--verbose", action="store_true", help="list misses and extras")
    args = parser.parse_args()
    settings = Settings(questionnaire_ocr="local")  # type: ignore[call-arg]

    totals = [0, 0, 0]
    header = f"{'file':<58} {'extractor':<12} {'status':<14}"
    print(f"{header} {'exp':>4} {'got':>4} {'prec':>5} {'rec':>5}")
    for key_path in sorted((args.corpus / "answer-keys").glob("*.json")):
        answer = json.loads(key_path.read_text(encoding="utf-8"))
        path = args.corpus / "questionnaires" / answer["file"]
        data = path.read_bytes()
        try:
            kind, content_type = detect_kind(path.name, data)
            extraction = await extract_questionnaire(kind, data, content_type, settings)
        except IngestError as exc:
            print(f"{path.name:<58} {'-':<12} {'error ' + exc.code:<14}")
            continue
        status = "ok"
        if extraction.needs_mapping and answer.get("user_mapping"):
            # Same path as the UI: the user picks the columns, extraction re-runs.
            extraction = await extract_questionnaire(
                kind, data, content_type, settings, user_mapping=answer["user_mapping"]
            )
            status = "user-mapped"
        elif extraction.needs_mapping:
            status = "needs_mapping"
        result = score(answer["questions"], [q.text for q in extraction.questions])
        totals[0] += result.expected
        totals[1] += result.extracted
        totals[2] += result.matched
        print(
            f"{path.name[:57]:<58} {extraction.extractor:<12} {status:<14} {result.expected:>4} "
            f"{result.extracted:>4} {result.precision:>5.2f} {result.recall:>5.2f}"
        )
        if args.verbose:
            for text in result.missed:
                print(f"      missed: {text}")
            for text in result.spurious:
                print(f"      extra:  {text}")
    expected, extracted, matched = totals
    print(
        f"\nOVERALL  precision {matched / max(extracted, 1):.3f}  "
        f"recall {matched / max(expected, 1):.3f}  ({matched}/{expected} questions)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

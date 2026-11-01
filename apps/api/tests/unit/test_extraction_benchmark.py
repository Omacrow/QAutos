"""Extraction quality floor on the generated test corpus (all formats, local OCR)."""

import importlib.util
import json
from pathlib import Path

import pytest

from sqa.questionnaires.evaluate import score
from sqa.questionnaires.extract import extract_questionnaire
from sqa.questionnaires.readers import detect_kind
from tests.unit.test_questionnaires import SETTINGS

# Measured 2026-11-01: precision 1.000, recall 0.989 (173/175). The two misses are
# OCR recognition failures on one long scanned line. Floors leave room for noise.
MIN_PRECISION = 0.95
MIN_RECALL = 0.95


def _load_generator():  # type: ignore[no-untyped-def]
    path = Path(__file__).resolve().parents[2] / "scripts" / "make_test_corpus.py"
    spec = importlib.util.spec_from_file_location("make_test_corpus", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def corpus(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("corpus")
    generator = _load_generator()
    for build in (
        generator.caiq_xlsx, generator.sig_xlsx, generator.hecvat_xlsx, generator.no_header_xlsx,
        generator.docx_table, generator.docx_paragraphs, generator.pdf_questionnaire,
        generator.scanned, generator.csv_questionnaire, generator.xml_questionnaire,
    ):  # fmt: skip
        build(out)
    return out


async def test_extraction_meets_quality_floor(corpus: Path) -> None:
    expected = extracted = matched = 0
    misses: dict[str, list[str]] = {}
    for key_path in sorted((corpus / "answer-keys").glob("*.json")):
        answer = json.loads(key_path.read_text(encoding="utf-8"))
        data = (corpus / "questionnaires" / answer["file"]).read_bytes()
        kind, content_type = detect_kind(answer["file"], data)
        result = await extract_questionnaire(kind, data, content_type, SETTINGS)
        if result.needs_mapping and answer.get("user_mapping"):
            result = await extract_questionnaire(
                kind, data, content_type, SETTINGS, user_mapping=answer["user_mapping"]
            )
        found = score(answer["questions"], [q.text for q in result.questions])
        expected, extracted, matched = (
            expected + found.expected,
            extracted + found.extracted,
            matched + found.matched,
        )
        if found.missed or found.spurious:
            misses[answer["file"]] = found.missed + [f"extra: {s}" for s in found.spurious]
    assert matched / extracted >= MIN_PRECISION, misses
    assert matched / expected >= MIN_RECALL, misses

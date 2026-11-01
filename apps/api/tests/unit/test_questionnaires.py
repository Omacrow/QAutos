import os

import pytest

from sqa.core.config import Settings
from sqa.ingestion.types import IngestError
from sqa.models import QuestionnaireKind
from sqa.questionnaires.evaluate import score
from sqa.questionnaires.extract import extract_questionnaire
from sqa.questionnaires.heuristics import (
    column_letter,
    is_answer_label,
    is_question_sentence,
    looks_like_question,
    split_ref,
)
from sqa.questionnaires.lines import HeuristicLineClassifier, Line, LineLabel, extract_from_lines
from sqa.questionnaires.ocr import repair_ocr_text
from sqa.questionnaires.readers import detect_kind
from sqa.questionnaires.tabular import SheetMapping, detect_mapping, extract_rows, sheet_locator
from tests.samples import make_docx, make_pdf, make_xlsx

SETTINGS = Settings(
    database_url=os.environ["DATABASE_URL"],  # type: ignore[arg-type]
    clerk_issuer="https://x",
)


# --- Text rules ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1.2 Do you encrypt backups?", ("1.2", "Do you encrypt backups?")),
        ("IAM-14.1 Is MFA enforced for staff?", ("IAM-14.1", "Is MFA enforced for staff?")),
        ("A&A-01.1 Are audits performed annually?", ("A&A-01.1", "Are audits performed annually?")),
        ("3) Describe your backup process.", ("3", "Describe your backup process.")),
        ("2FA is required for everyone here", (None, "2FA is required for everyone here")),
        ("24x7 monitoring of all systems", (None, "24x7 monitoring of all systems")),
    ],
)
def test_split_ref(text: str, expected: tuple[str | None, str]) -> None:
    assert split_ref(text) == expected


def test_question_rules() -> None:
    assert looks_like_question("Where is data stored")
    assert is_question_sentence("Please describe your incident response process.")
    assert not is_question_sentence("Please complete the table below.")
    assert not is_question_sentence("Do you?")  # too short
    assert is_answer_label("Response: ________")
    assert is_answer_label("Yes / No")
    assert not is_answer_label("Responsibilities are defined in the RACI.")


def test_column_letters() -> None:
    assert [column_letter(i) for i in (0, 25, 26, 27, 701)] == ["A", "Z", "AA", "AB", "ZZ"]


# --- Spreadsheet columns -----------------------------------------------------------------


def test_header_detection_prefers_question_over_question_id() -> None:
    grid = [
        ["Vendor Assessment"],
        [],
        ["Question ID", "Question", "CSP CAIQ Answer", "Comments"],
        ["Audit & Assurance"],
        ["A&A-01.1", "Are audits performed annually?", "", ""],
    ]
    mapping = detect_mapping("CAIQ", grid)
    assert mapping == SheetMapping(
        "CAIQ", 2, question_col=1, answer_col=2, ref_col=0, comment_col=3
    )
    rows = extract_rows(grid, mapping, sheet_locator("CAIQ"))
    assert len(rows) == 1
    question = rows[0]
    assert (question.ref, question.section) == ("A&A-01.1", "Audit & Assurance")
    assert question.locator == {
        "sheet": "CAIQ",
        "row": 5,
        "question_cell": "B5",
        "answer_cell": "C5",
    }


def test_sheet_without_header_needs_mapping() -> None:
    assert detect_mapping("S", [["Do you encrypt data?", ""], ["Is MFA on?", ""]]) is None


def test_label_rows_become_sections_but_questions_are_never_lost() -> None:
    grid = [
        ["#", "Question", "Answer"],
        ["", "ACCESS CONTROL", ""],
        ["1", "Is MFA enforced?", ""],
        ["", "Password policy", ""],  # no ref, short, not a question: a label
        ["2", "Password rotation", ""],  # has a ref: kept as a question
    ]
    mapping = detect_mapping("S", grid)
    assert mapping is not None
    rows = extract_rows(grid, mapping, sheet_locator("S"))
    assert [(q.ref, q.text, q.section) for q in rows] == [
        ("1", "Is MFA enforced?", "ACCESS CONTROL"),
        ("2", "Password rotation", "Password policy"),
    ]


# --- Lines (PDF text / OCR) ------------------------------------------------------------


def _lines(*texts: str, size: float = 10) -> list[Line]:
    return [Line(text=t, page=1, size=size) for t in texts]


def test_lines_join_wrapped_questions_and_skip_instructions() -> None:
    lines = [
        Line("Section 1: Access", 1, 14, bold=True),
        *_lines(
            "Please answer every question below.",
            "1.1 Within what timeframe will customers be notified of a security",
            "incident affecting their data?",
            "Response: ________",
            "1.2 Describe your access review process.",
        ),
    ]
    found = extract_from_lines(lines)
    assert [(q.ref, q.text, q.section) for q in found] == [
        (
            "1.1",
            "Within what timeframe will customers be notified of a security incident "
            "affecting their data?",
            "Section 1: Access",
        ),
        ("1.2", "Describe your access review process.", "Section 1: Access"),
    ]
    assert found[0].locator == {"page": 1}


def test_classifier_labels() -> None:
    classify = HeuristicLineClassifier().classify
    assert classify(Line("ACCESS CONTROL", 1, 10), 10) is LineLabel.SECTION
    assert classify(Line("1.5 ls privileged access logged?", 1, 10), 10) is LineLabel.QUESTION
    assert classify(Line("Answer:", 1, 10), 10) is LineLabel.ANSWER
    assert classify(Line("Page 3 of 9", 1, 8), 10) is LineLabel.OTHER


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("1.1lsmulti-factorauthenticationrequired", "1.1 Is multi-factor authentication required"),
        (
            "Howquickly is access revokedwhenan employee leaves",
            "How quickly is access revoked when an employee leaves",
        ),
        ("lnformation security", "Information security"),
        ("Response:", "Response:"),
    ],
)
def test_ocr_repair(raw: str, clean: str) -> None:
    assert repair_ocr_text(raw) == clean


# --- Formats end to end ----------------------------------------------------------------


async def _extract(name: str, data: bytes, **kwargs: object):  # type: ignore[no-untyped-def]
    kind, content_type = detect_kind(name, data)
    return await extract_questionnaire(kind, data, content_type, SETTINGS, **kwargs)  # type: ignore[arg-type]


async def test_xlsx_skips_sheets_without_questions() -> None:
    data = make_xlsx(
        {
            "Instructions": [["Answer every question."]],
            "Q": [["ID", "Question", "Response"], ["1", "Do you encrypt backups?", ""]],
        }
    )
    result = await _extract("q.xlsx", data)
    assert [q.text for q in result.questions] == ["Do you encrypt backups?"]
    assert result.mapping is not None
    assert [m["sheet"] for m in result.mapping["sheets"]] == ["Q"]


async def test_user_mapping_without_header_row() -> None:
    data = make_xlsx({"Sheet1": [["Do you encrypt backups?", ""], ["Is MFA enforced?", ""]]})
    detected = await _extract("q.xlsx", data)
    assert detected.needs_mapping
    assert detected.preview is not None
    mapped = await _extract(
        "q.xlsx",
        data,
        user_mapping={
            "sheets": [{"sheet": "Sheet1", "header_row": None, "question_col": 0, "answer_col": 1}]
        },
    )
    assert [q.text for q in mapped.questions] == ["Do you encrypt backups?", "Is MFA enforced?"]
    assert mapped.questions[0].locator["answer_cell"] == "B1"


async def test_csv_with_semicolons() -> None:
    data = b"ID;Question;Answer\n1;Is data encrypted at rest?;\n2;Do you log access?;\n"
    result = await _extract("q.csv", data)
    assert [(q.ref, q.text) for q in result.questions] == [
        ("1", "Is data encrypted at rest?"),
        ("2", "Do you log access?"),
    ]


async def test_docx_tables_and_numbered_paragraphs() -> None:
    data = make_docx(
        [
            ("p", "Please complete the table below."),
            ("table", "No.|Question|Response"),
            ("table", "1|Do you have a CISO?|"),
            ("h1", "Narrative"),
            ("p", "2. Describe your backup strategy in detail."),
            ("p", "Answer:"),
        ]
    )
    result = await _extract("q.docx", data)
    texts = [q.text for q in result.questions]
    assert "Describe your backup strategy in detail." in texts
    assert "Please complete the table below." not in texts


async def test_text_pdf() -> None:
    data = make_pdf(
        [
            [
                ("Section 1: Security", 14, True),
                ("1.1 Do you have an incident response plan?", 10.5, False),
                ("Response: ______", 10, False),
                ("1.2 How long are logs retained?", 10.5, False),
            ]
        ]
    )
    result = await _extract("q.pdf", data)
    assert result.extractor == "pdf-text"
    assert [(q.ref, q.section) for q in result.questions] == [
        ("1.1", "Section 1: Security"),
        ("1.2", "Section 1: Security"),
    ]


async def test_xml_refuses_entities() -> None:
    evil = b'<?xml version="1.0"?><!DOCTYPE q [<!ENTITY x SYSTEM "file:///etc/passwd">]><q>&x;</q>'
    with pytest.raises(IngestError) as exc:
        await _extract("q.xml", evil)
    assert exc.value.code == "corrupt"


async def test_xml_questions_with_sections() -> None:
    data = (
        b'<questionnaire><section name="Crypto"><question id="C-1">Is data encrypted at rest?'
        b"</question></section></questionnaire>"
    )
    result = await _extract("q.xml", data)
    assert [(q.ref, q.section, q.text) for q in result.questions] == [
        ("C-1", "Crypto", "Is data encrypted at rest?")
    ]


async def test_scans_need_an_engine_when_ocr_is_off() -> None:
    import pymupdf

    doc = pymupdf.open()
    doc.new_page().draw_rect(pymupdf.Rect(10, 10, 50, 50), fill=(0, 0, 0))
    settings = SETTINGS.model_copy(update={"questionnaire_ocr": "none"})
    kind, content_type = detect_kind("scan.pdf", doc.tobytes())
    with pytest.raises(IngestError) as exc:
        await extract_questionnaire(kind, doc.tobytes(), content_type, settings)
    assert exc.value.code == "no_text"
    claude = SETTINGS.model_copy(update={"questionnaire_ocr": "claude"})
    with pytest.raises(IngestError) as exc:
        await extract_questionnaire(kind, doc.tobytes(), content_type, claude)  # no key, no engine
    assert exc.value.code == "vision_unavailable"


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("q.png", b"\xff\xd8\xff not a png"),
        ("q.jpg", b"\x89PNG\r\n\x1a\n not a jpeg"),
        ("q.exe", b"MZ"),
        ("q.xml", b"just text"),
    ],
)
def test_detect_kind_rejects(name: str, data: bytes) -> None:
    with pytest.raises(IngestError):
        detect_kind(name, data)


def test_detect_kind_images() -> None:
    assert detect_kind("scan.PNG", b"\x89PNG\r\n\x1a\n...") == (
        QuestionnaireKind.IMAGE,
        "image/png",
    )
    assert detect_kind("scan.jpeg", b"\xff\xd8\xff...") == (QuestionnaireKind.IMAGE, "image/jpeg")


# --- Scoring -----------------------------------------------------------------------------


def test_extraction_score_is_fuzzy_and_one_to_one() -> None:
    expected = ["Do you encrypt backups?", "Is MFA enforced?"]
    result = score(
        expected, ["Do you encrypt backups ?", "Do you encrypt backups?", "Random heading"]
    )
    assert result.matched == 1
    assert result.missed == ["Is MFA enforced?"]
    assert len(result.spurious) == 2
    assert result.precision == pytest.approx(1 / 3)
    assert result.recall == 0.5

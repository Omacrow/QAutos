import io
import zipfile

import pymupdf
import pytest

from sqa.ingestion.docx import convert_to_pdf, find_soffice, parse_docx
from sqa.ingestion.pdf import parse_pdf
from sqa.ingestion.types import IngestError
from sqa.ingestion.validate import detect_kind, safe_filename
from sqa.ingestion.xlsx import parse_xlsx
from sqa.models import DocumentKind
from tests.samples import make_docx, make_pdf, make_xlsx

BODY = 10.5


def _pdf_policy() -> bytes:
    return make_pdf(
        [
            [
                ("Security Policy", 22, False),
                ("Access Control", 16, True),
                ("Access is reviewed every quarter by system owners.", BODY, False),
                ("Passwords", 13, True),
                ("MFA is required for every employee account.", BODY, False),
            ],
            [
                ("Encryption", 16, True),
                ("Data at rest is encrypted with AES-256.", BODY, False),
            ],
            [("Backups are tested monthly.", BODY, False)],
        ],
        header="Acme Corp - Confidential",
        footer=True,
    )


# --- PDF ----------------------------------------------------------------------


def test_pdf_pages_and_headings_from_font_sizes() -> None:
    parsed = parse_pdf(_pdf_policy(), max_pages=100)
    found = {b.text: (b.page, b.heading_path) for b in parsed.blocks}
    assert parsed.page_count == 3
    assert found["Access is reviewed every quarter by system owners."] == (
        1,
        ("Security Policy", "Access Control"),
    )
    assert found["MFA is required for every employee account."] == (
        1,
        ("Security Policy", "Access Control", "Passwords"),
    )
    assert found["Data at rest is encrypted with AES-256."] == (
        2,
        ("Security Policy", "Encryption"),
    )
    # A section carries over to the next page until a new heading starts.
    assert found["Backups are tested monthly."] == (3, ("Security Policy", "Encryption"))


def test_pdf_drops_running_headers_and_footers() -> None:
    text = " ".join(b.text for b in parse_pdf(_pdf_policy(), max_pages=100).blocks)
    assert "Confidential" not in text
    assert "Page" not in text


def test_pdf_outline_wins_over_font_guessing() -> None:
    # Every line is the same size, so only the outline can identify headings.
    data = make_pdf(
        [
            [("Overview", BODY, False), ("We are a payroll company.", BODY, False)],
            [("Retention", BODY, False), ("Logs are kept for one year.", BODY, False)],
        ],
        toc=[[1, "Overview", 1], [1, "Retention", 2]],
    )
    found = {b.text: (b.page, b.heading_path) for b in parse_pdf(data, max_pages=10).blocks}
    assert found == {
        "We are a payroll company.": (1, ("Overview",)),
        "Logs are kept for one year.": (2, ("Retention",)),
    }


def test_pdf_page_limit() -> None:
    data = make_pdf([[("x", BODY, False)]] * 3)
    with pytest.raises(IngestError) as exc:
        parse_pdf(data, max_pages=2)
    assert exc.value.code == "too_many_pages"


def test_pdf_without_text_is_rejected() -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    page.draw_rect(pymupdf.Rect(50, 50, 200, 200), fill=(0, 0, 0))  # a "scan": no text layer
    data = doc.tobytes()
    with pytest.raises(IngestError) as exc:
        parse_pdf(data, max_pages=10)
    assert exc.value.code == "no_text"


def test_encrypted_pdf_is_rejected() -> None:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "secret")
    data = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="pw2")
    with pytest.raises(IngestError) as exc:
        parse_pdf(data, max_pages=10)
    assert exc.value.code == "encrypted"


# --- DOCX ---------------------------------------------------------------------


def test_docx_headings_tables_and_page_breaks() -> None:
    data = make_docx(
        [
            ("h1", "Business Continuity"),
            ("p", "Our RTO is four hours."),
            ("h2", "Backups"),
            ("p", "Backups run nightly."),
            ("table", "System|RPO"),
            ("h1", "Contacts"),
            ("p", "Call the on-call engineer."),
        ],
        page_break_after={4},
    )
    parsed = parse_docx(data)
    found = {b.text: (b.page, b.heading_path) for b in parsed.blocks}
    assert found["Our RTO is four hours."] == (1, ("Business Continuity",))
    assert found["Backups run nightly."] == (1, ("Business Continuity", "Backups"))
    assert found["System | RPO"] == (1, ("Business Continuity", "Backups"))
    assert found["Call the on-call engineer."] == (2, ("Contacts",))
    assert parsed.parser == "python-docx"


@pytest.mark.skipif(find_soffice() is None, reason="LibreOffice not installed")
def test_docx_converts_to_pdf_with_libreoffice() -> None:
    soffice = find_soffice()
    assert soffice is not None
    pdf = convert_to_pdf(make_docx([("h1", "Intro"), ("p", "Hello there.")]), soffice)
    assert pdf.startswith(b"%PDF-")


# --- XLSX ---------------------------------------------------------------------


def test_xlsx_rows_are_labelled_with_headers() -> None:
    data = make_xlsx(
        {
            "Answers": [
                ["Question", "Answer"],
                ["Do you encrypt backups?", "Yes, AES-256"],
                [None, None],
                ["Is MFA enforced?", "Yes"],
            ],
            "Internal": [["secret", "row"]],
        },
        hidden=frozenset({"Internal"}),
    )
    parsed = parse_xlsx(data, max_rows=100)
    assert [(b.sheet, b.row, b.text) for b in parsed.blocks] == [
        ("Answers", 2, "Question: Do you encrypt backups? | Answer: Yes, AES-256"),
        ("Answers", 4, "Question: Is MFA enforced? | Answer: Yes"),
    ]


def test_xlsx_row_limit() -> None:
    data = make_xlsx({"S": [["Q", "A"]] + [[f"q{i}", "a"] for i in range(10)]})
    with pytest.raises(IngestError) as exc:
        parse_xlsx(data, max_rows=5)
    assert exc.value.code == "too_large"


# --- Validation -----------------------------------------------------------------


def test_detect_kind_by_content() -> None:
    assert detect_kind("a.pdf", _pdf_policy()) is DocumentKind.PDF
    assert detect_kind("a.DOCX", make_docx([("p", "x")])) is DocumentKind.DOCX
    assert detect_kind("a.xlsx", make_xlsx({"S": [["a", "b"]]})) is DocumentKind.XLSX


@pytest.mark.parametrize(
    ("filename", "data", "code"),
    [
        ("notes.txt", b"hello", "unsupported_type"),
        ("fake.pdf", b"MZ\x90\x00 not a pdf", "unsupported_type"),
        ("fake.docx", b"PK\x03\x04garbage", "corrupt"),
    ],
)
def test_detect_kind_rejects(filename: str, data: bytes, code: str) -> None:
    with pytest.raises(IngestError) as exc:
        detect_kind(filename, data)
    assert exc.value.code == code


def test_xlsx_renamed_to_docx_is_rejected() -> None:
    with pytest.raises(IngestError) as exc:
        detect_kind("report.docx", make_xlsx({"S": [["a", "b"]]}))
    assert exc.value.code == "unsupported_type"


def _zip(entries: dict[str, bytes]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return out.getvalue()


def test_macros_are_rejected() -> None:
    data = _zip(
        {"[Content_Types].xml": b"<x/>", "word/document.xml": b"<x/>", "word/vbaProject.bin": b"1"}
    )
    with pytest.raises(IngestError) as exc:
        detect_kind("a.docx", data)
    assert exc.value.code == "macros_not_allowed"


def test_zip_bombs_are_rejected() -> None:
    data = _zip(
        {
            "[Content_Types].xml": b"<x/>",
            "word/document.xml": b"<x/>",
            "word/media/blob.bin": b"\0" * (5 * 1024 * 1024),  # compresses ~1000:1
        }
    )
    with pytest.raises(IngestError) as exc:
        detect_kind("a.docx", data)
    assert exc.value.code == "too_large"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("../../etc/passwd.pdf", "passwd.pdf"),
        ("C:\\Users\\me\\Policy.pdf", "Policy.pdf"),
        ('bad"name<>.pdf', "badname.pdf"),
        ("", "document"),
    ],
)
def test_safe_filename(raw: str, expected: str) -> None:
    assert safe_filename(raw) == expected

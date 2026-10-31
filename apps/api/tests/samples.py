"""Builders for small test documents."""

import io

import pymupdf
from docx import Document as new_docx
from openpyxl import Workbook


def make_pdf(
    pages: list[list[tuple[str, float, bool]]],
    *,
    header: str | None = None,
    footer: bool = False,
    toc: list[list[int | str]] | None = None,
) -> bytes:
    """Each page is a list of (text, font size, bold) lines, laid out top to bottom."""
    doc = pymupdf.open()
    for number, lines in enumerate(pages, start=1):
        page = doc.new_page()
        y = 90.0
        for text, size, bold in lines:
            page.insert_text((72, y), text, fontsize=size, fontname="hebo" if bold else "helv")
            y += size + 14
        if header:
            page.insert_text((72, 40), header, fontsize=8)
        if footer:
            page.insert_text((480, 805), f"Page {number} of {len(pages)}", fontsize=8)
    if toc:
        doc.set_toc(toc)
    data: bytes = doc.tobytes()
    doc.close()
    return data


def make_docx(
    items: list[tuple[str, str]], *, page_break_after: frozenset[int] = frozenset()
) -> bytes:
    """Items are (style, text): "h1"/"h2" headings, "p" body, "table" a row like "a|b"."""
    document = new_docx()
    for index, (style, text) in enumerate(items):
        if style in ("h1", "h2"):
            document.add_heading(text, level=int(style[1]))
        elif style == "table":
            cells = text.split("|")
            table = document.add_table(rows=1, cols=len(cells))
            for cell, value in zip(table.rows[0].cells, cells, strict=True):
                cell.text = value
        else:
            document.add_paragraph(text)
        if index in page_break_after:
            document.add_page_break()
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def make_xlsx(
    sheets: dict[str, list[list[object]]], *, hidden: frozenset[str] = frozenset()
) -> bytes:
    workbook = Workbook()
    workbook.remove(workbook.active)  # type: ignore[arg-type]
    for name, rows in sheets.items():
        sheet = workbook.create_sheet(name)
        for row in rows:
            sheet.append(row)
        if name in hidden:
            sheet.sheet_state = "hidden"
    out = io.BytesIO()
    workbook.save(out)
    return out.getvalue()

"""Reading scanned questionnaires: local OCR by default, Claude vision as an option.

Local OCR uses RapidOCR: PaddleOCR's detection and recognition models run on
ONNX Runtime, on CPU, with no network access and no GPU. It returns text lines
with boxes; `lines.extract_from_lines` then finds the questions, exactly as for
PDFs that have a text layer.
"""

import asyncio
import re
import threading
from typing import Any

import pymupdf
import wordninja

from sqa.ingestion.types import IngestError
from sqa.questionnaires.lines import Line

RENDER_DPI = 250
MAX_IMAGE_SIDE = 4000
# The text detector misses lines in small images; scale them up to about this size.
MIN_IMAGE_SIDE = 2400
MAX_UPSCALE = 2.5
# Runs of letters this long are almost always several words the OCR ran together.
_RUN_ON = re.compile(r"[A-Za-z]{9,}")
# The first word after a question number is where run-ons cluster ("Ismulti").
_FIRST_WORD = re.compile(r"^((?:\d+(?:\.\d+)*\.?\s)?)([A-Za-z]{5,8})(?=\b)")
_REF_THEN_WORD = re.compile(r"^(\d+(?:\.\d+)*\.?)(?=[A-Za-z])")
# PaddleOCR often reads a capital I as a lowercase l at the start of a sentence.
_L_FOR_I = re.compile(r"^((?:\d+(?:\.\d+)*\.?\s*)?)l(?=[sftn])")


def repair_ocr_text(text: str) -> str:
    """Undo the OCR model's common slips: missing spaces and l/I confusion.

    "1.1lsmulti-factorauthenticationrequired" -> "1.1 Is multi-factor authentication required"
    """
    text = _L_FOR_I.sub(r"\1I", text)
    text = _REF_THEN_WORD.sub(r"\1 ", text)

    text = _FIRST_WORD.sub(lambda m: m.group(1) + _split_words(m.group(2)), text)
    return " ".join(_RUN_ON.sub(lambda m: _split_words(m.group(0)), text).split())


def _split_words(run: str) -> str:
    words = wordninja.split(run)
    return " ".join(words) if words else run


_engine: Any = None
_engine_lock = threading.Lock()


def _rapidocr() -> Any:
    """One shared engine per process: loading the models takes about a second."""
    global _engine
    with _engine_lock:
        if _engine is None:
            from rapidocr_onnxruntime import RapidOCR

            _engine = RapidOCR()
        return _engine


def page_images(data: bytes, *, is_pdf: bool, max_pages: int) -> list[bytes]:
    """PNG bytes per page: PDF pages rendered at 200 dpi, or the image itself (downscaled)."""
    if is_pdf:
        try:
            doc = pymupdf.open(stream=data, filetype="pdf")
        except Exception:
            raise IngestError("corrupt") from None
        with doc:
            if doc.page_count > max_pages:
                raise IngestError("too_many_pages")
            return [doc[i].get_pixmap(dpi=RENDER_DPI).tobytes("png") for i in range(doc.page_count)]
    try:
        pixmap = pymupdf.Pixmap(data)
    except Exception:
        raise IngestError("corrupt") from None
    if pixmap.alpha:
        pixmap = pymupdf.Pixmap(pixmap, 0)  # drop transparency
    longest = max(pixmap.width, pixmap.height)
    if longest > MAX_IMAGE_SIDE:
        pixmap.shrink(1 if longest <= MAX_IMAGE_SIDE * 2 else 2)
    elif longest < MIN_IMAGE_SIDE:
        scale = min(MIN_IMAGE_SIDE / longest, MAX_UPSCALE)
        pixmap = pymupdf.Pixmap(pixmap, int(pixmap.width * scale), int(pixmap.height * scale))
    png: bytes = pixmap.tobytes("png")
    return [png]


def ocr_lines(images: list[bytes]) -> list[Line]:
    """Text lines in reading order, with the box height standing in for font size."""
    engine = _rapidocr()
    lines: list[Line] = []
    for page_number, image in enumerate(images, start=1):
        result, _ = engine(image)
        boxes = [
            (min(p[1] for p in box), max(p[1] for p in box), min(p[0] for p in box), text)
            for box, text, _score in (result or [])
        ]
        lines.extend(_merge_rows(boxes, page_number))
    return lines


def _merge_rows(boxes: list[tuple[float, float, float, str]], page: int) -> list[Line]:
    """OCR can split one printed line into several boxes: join boxes sharing a row."""
    boxes.sort(key=lambda b: (b[0], b[2]))
    rows: list[list[tuple[float, float, float, str]]] = []
    for box in boxes:
        top, bottom = box[0], box[1]
        if rows:
            last = rows[-1]
            last_top = min(b[0] for b in last)
            last_bottom = max(b[1] for b in last)
            overlap = min(bottom, last_bottom) - max(top, last_top)
            if overlap > 0.5 * min(bottom - top, last_bottom - last_top):
                last.append(box)
                continue
        rows.append([box])
    out = []
    for row in rows:
        row.sort(key=lambda b: b[2])
        height = max(b[1] for b in row) - min(b[0] for b in row)
        text = repair_ocr_text(" ".join(b[3] for b in row))
        out.append(Line(text=text, page=page, size=height))
    return out


async def ocr_document(data: bytes, *, is_pdf: bool, max_pages: int) -> list[Line]:
    """CPU-bound: runs in a worker thread so the event loop stays responsive."""

    def run() -> list[Line]:
        return ocr_lines(page_images(data, is_pdf=is_pdf, max_pages=max_pages))

    return await asyncio.to_thread(run)

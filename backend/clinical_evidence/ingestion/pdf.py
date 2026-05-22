"""PDF ingestion via PyMuPDF with OCR fallback for scanned pages."""

from __future__ import annotations

import io
import logging

log = logging.getLogger(__name__)


def extract_text(pdf_bytes: bytes) -> str:
    """Return concatenated text from a PDF. OCR is used for empty pages."""
    try:
        import fitz  # PyMuPDF
    except ImportError:  # pragma: no cover
        log.warning("PyMuPDF not installed; returning empty PDF text.")
        return ""

    out: list[str] = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            text = page.get_text("text") or ""
            if text.strip():
                out.append(text)
                continue
            ocr = _ocr_page(page)
            if ocr:
                out.append(ocr)
    return "\n\n".join(out)


def _ocr_page(page) -> str:  # pragma: no cover - depends on optional deps
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return ""
    pix = page.get_pixmap(dpi=200)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    try:
        return pytesseract.image_to_string(img)
    except Exception as exc:  # noqa: BLE001
        log.warning("OCR failed: %s", exc)
        return ""

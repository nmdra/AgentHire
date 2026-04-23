"""Improved PDF parsing tool with OCR and layout detection."""

from __future__ import annotations

import io
import re
from pathlib import Path

import pymupdf

try:
    import pymupdf4llm
except ImportError:  # pragma: no cover - optional dependency fallback
    pymupdf4llm = None

try:
    import pytesseract
except ImportError:  # pragma: no cover - optional dependency fallback
    pytesseract = None

try:
    from PIL import Image
except ImportError:  # pragma: no cover - optional dependency fallback
    Image = None

from langchain.tools import tool

from app.logger import setup_logger

logger = setup_logger("parse_pdf_tool")


def _clean_ocr_text(text: str) -> str:
    """Apply regex cleaning to OCR/extracted text to improve LLM compatibility."""
    # Remove markdown table syntax
    text = re.sub(r"\|[-:]+\|[-| :]*", "", text)
    text = re.sub(r"\|.*?\|", lambda m: m.group().replace("|", " ").strip(), text)

    # Remove excessive markdown formatting
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"\*{2,}(.*?)\*{2,}", r"\1", text)
    text = re.sub(r"\*(.*?)\*", r"\1", text)
    text = re.sub(r"`{1,3}(.*?)`{1,3}", r"\1", text)

    # Fix spaced characters (OCR artifact)
    text = re.sub(
        r"\b([A-Z])\s([A-Z])\s([A-Z])\s([A-Z])",
        lambda m: m.group().replace(" ", ""),
        text,
    )

    # Fix broken words across lines
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)

    # Normalise bullet points
    text = re.sub(
        r"^[\u2022\u2023\u25e6\u2043\u2219■►◆●»]\s*", "- ", text, flags=re.MULTILINE
    )

    # Fix email artifacts
    text = re.sub(r"\s@\s", "@", text)
    text = re.sub(r"\(at\)", "@", text)
    text = re.sub(r"(\w)\s\.\s(\w)", r"\1.\2", text)

    # Fix phone number artifacts
    text = re.sub(r"(\d)\s(\d{3})\s(\d{4})", r"\1\2\3", text)

    # Remove form feed and page markers
    text = re.sub(r"\f", "\n", text)
    text = re.sub(r"\[Page \d+\]", "", text)
    text = re.sub(r"-----.*?-----", "", text)

    # Collapse 3+ blank lines into 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Strip leading/trailing whitespace per line
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)

    return text.strip()


def _detect_column_count(doc: pymupdf.Document) -> int:
    """Return 1 or 2 — detect if resume uses two-column layout on the first page."""
    if len(doc) == 0:
        return 1
    page = doc[0]
    width = page.rect.width
    mid = width / 2

    blocks = page.get_text("blocks")
    left_blocks = [b for b in blocks if b[2] < mid]  # x1 < midpoint
    right_blocks = [b for b in blocks if b[0] > mid]  # x0 > midpoint

    return 2 if len(left_blocks) > 2 and len(right_blocks) > 2 else 1


def _fix_two_column_layout(doc: pymupdf.Document) -> str:
    """Extract text by columns to handle two-column layouts more reliably."""
    full_text = []
    for page in doc:
        width = page.rect.width
        midpoint = width / 2

        left_clip = pymupdf.Rect(0, 0, midpoint, page.rect.height)
        right_clip = pymupdf.Rect(midpoint, 0, width, page.rect.height)

        left_text = page.get_text("text", clip=left_clip).strip()
        right_text = page.get_text("text", clip=right_clip).strip()

        if left_text and right_text:
            full_text.append(left_text + "\n\n" + right_text)
        else:
            full_text.append(left_text or right_text)
    return "\n\n".join(full_text)


def _is_garbled(text: str) -> bool:
    """Detect if the extracted text is too garbled or sparse to be useful."""
    content = text.strip()
    if len(content) < 50:
        return True
    non_ascii = sum(1 for c in content if ord(c) > 127)
    if non_ascii / max(len(content), 1) > 0.3:
        return True
    return not bool(re.search(r"[A-Za-z]{3,}", content))


def _ocr_scanned_pdf(doc: pymupdf.Document) -> str:
    """Extract text from scanned PDF using pytesseract OCR."""
    if pytesseract is None or Image is None:
        raise RuntimeError("OCR dependencies are not installed")

    pages_text = []
    for page in doc:
        mat = pymupdf.Matrix(300 / 72, 300 / 72)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.open(io.BytesIO(pix.tobytes("png")))

        text = pytesseract.image_to_string(img, config="--psm 6 --oem 3", lang="eng")
        pages_text.append(text)
    return "\n\n".join(pages_text)


@tool
def parse_pdf_tool(path: str) -> str:
    """Extract cleaned text from a PDF file using layout detection and OCR fallbacks.

    Args:
        path: Absolute file path to a PDF.

    Returns:
        Extracted and cleaned text.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"File does not exist: {path}")

    logger.info(f"Starting extraction for {path}")
    doc = pymupdf.open(path)

    # Check if scanned
    total_chars = sum(len(page.get_text()) for page in doc)
    if total_chars < 100:
        logger.info("Scanned PDF detected, attempting OCR fallback")
        try:
            text = _ocr_scanned_pdf(doc)
        except (pytesseract.TesseractNotFoundError, OSError) as exc:
            logger.warning(f"OCR skipped: Tesseract binary not found or unusable ({exc}).")
            text = "\n\n".join(page.get_text("text") for page in doc)
        except Exception as exc:
            logger.error(f"OCR failed due to unexpected error: {exc}")
            text = "\n\n".join(page.get_text("text") for page in doc)
    else:
        # Check column count
        col_count = _detect_column_count(doc)
        if col_count == 2:
            logger.info("Two-column layout detected")
            text = _fix_two_column_layout(doc)
        else:
            logger.info("Single-column layout detected")
            if pymupdf4llm is not None:
                chunks = pymupdf4llm.to_markdown(
                    path,
                    page_chunks=True,
                    show_toc=False,
                    embed_images=False,
                    table_strategy="lines",
                )
                if chunks and isinstance(chunks[0], dict):
                    text = "\n\n".join(chunk["text"] for chunk in chunks)
                else:
                    text = "\n\n".join(str(c) for c in chunks)
            else:
                text = "\n\n".join(page.get_text("text") for page in doc)

    # Layer 2 cleaning
    text = _clean_ocr_text(text)

    # Fallback to raw extraction if still garbled
    if _is_garbled(text):
        logger.warning("Extraction result looks garbled, falling back to raw text")
        text = "\n\n".join(page.get_text("text") for page in doc)
        text = _clean_ocr_text(text)

    doc.close()

    if not text.strip():
        raise ValueError("No text could be extracted from PDF")

    logger.info(f"Successfully extracted {len(text)} characters")
    return text

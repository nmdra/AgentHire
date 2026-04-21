"""PDF parsing tool."""

from __future__ import annotations

from pathlib import Path

from langchain.tools import tool
import pymupdf4llm


@tool
def parse_pdf_tool(path: str) -> str:
    """Extract text from a PDF file.

    Args:
        path: Absolute file path to a PDF.

    Returns:
        Extracted text.

    Raises:
        FileNotFoundError: If the file is missing.
        ValueError: If no text is extracted.

    Example:
        parse_pdf_tool.invoke({"path": "/tmp/resume.pdf"})
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"File does not exist: {path}")

    text = str(pymupdf4llm.to_markdown(path))

    cleaned = text.strip()
    if not cleaned:
        raise ValueError("No text could be extracted from PDF")
    return cleaned

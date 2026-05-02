"""Plain-text parsing tools."""

from __future__ import annotations

from pathlib import Path

from langchain.tools import tool


@tool
def parse_text_tool(path: str) -> str:
    """Read UTF-8 text from a plain text file.

    Args:
        path: Absolute file path to a text-like file.

    Returns:
        File content as text.

    Raises:
        FileNotFoundError: If the file is missing.

    Example:
        parse_text_tool.invoke({"path": "/tmp/application.txt"})
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"File does not exist: {path}")
    return file_path.read_text(encoding="utf-8-sig")

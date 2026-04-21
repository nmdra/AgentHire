"""JSON parsing tools."""

from __future__ import annotations

import json
from pathlib import Path

from langchain.tools import tool


@tool
def parse_json_tool(path: str) -> str:
    """Read and normalize a JSON file as pretty text.

    Args:
        path: Absolute file path to JSON input.

    Returns:
        JSON string representation.

    Raises:
        FileNotFoundError: If the file is missing.
        ValueError: If file content is invalid JSON.

    Example:
        parse_json_tool.invoke({"path": "/tmp/application.json"})
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"File does not exist: {path}")

    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid JSON input file") from exc
    return json.dumps(payload, indent=2, ensure_ascii=False)

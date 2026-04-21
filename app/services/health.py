from __future__ import annotations

from urllib.parse import urlparse
import urllib.request

from app.tools.database import connect


def check_db(db_path: str) -> str:
    try:
        with connect(db_path) as conn:
            conn.execute("SELECT 1")
        return "ok"
    except Exception:
        return "down"


def check_ollama(ollama_base_url: str) -> str:
    parsed = urlparse(ollama_base_url)
    if parsed.scheme not in {"http", "https"}:
        return "down"
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        return "down"
    try:
        with urllib.request.urlopen(f"{ollama_base_url}/api/tags", timeout=2) as response:
            if response.status == 200:
                return "ok"
    except Exception:
        return "down"
    return "down"

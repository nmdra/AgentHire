"""Runtime configuration for AgentHire."""

from __future__ import annotations

from dataclasses import dataclass
from os import getenv

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables."""

    db_path: str = getenv("DB_PATH", "agenthire.db")
    uploads_dir: str = getenv("UPLOADS_DIR", "uploads")
    reports_dir: str = getenv("REPORTS_DIR", "reports")
    max_upload_size_bytes: int = int(getenv("MAX_UPLOAD_SIZE_BYTES", "10485760"))
    ollama_base_url: str = getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    extraction_model: str = getenv("EXTRACTION_MODEL", "smollm:360m")
    ollama_timeout_seconds: float = float(getenv("OLLAMA_TIMEOUT_SECONDS", "30"))
    resend_api_key: str = getenv("RESEND_API_KEY", "")
    resend_from_email: str = getenv("RESEND_FROM_EMAIL", "noreply@example.com")


def get_settings() -> Settings:
    """Return singleton-like settings object."""
    return Settings()

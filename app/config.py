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
    extraction_model: str = getenv(
        "EXTRACTION_MODEL",
        "hf.co/nimendraai/NuExtract-tiny-Resume-Data-Extractor:Q4_K_M",
    )
    evaluation_model: str = getenv("EVALUATION_MODEL", "gemma3:1b-it-q4_K_M")
    validation_model: str = getenv("VALIDATION_MODEL", "gemma3:1b-it-q4_K_M")
    ollama_timeout_seconds: float = float(getenv("OLLAMA_TIMEOUT_SECONDS", "120"))
    ollama_num_ctx: int = int(getenv("OLLAMA_NUM_CTX", "4096"))
    default_rubric_path: str = getenv(
        "DEFAULT_RUBRIC_PATH", "data/default_rubric.json"
    )
    debug_logs: bool = getenv("DEBUG_LOGS", "false").lower() in ("true", "1", "yes")

    # External Services
    resend_api_key: str | None = getenv("RESEND_API_KEY")
    resend_from_email: str = getenv("RESEND_FROM_EMAIL", "delivered@resend.dev")
    reviewer_email: str = getenv("REVIEWER_EMAIL", "admin@example.com")


def get_settings() -> Settings:
    """Return singleton-like settings object."""
    return Settings()

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AgentHire"
    db_path: str = "agenthire.db"
    uploads_dir: str = "uploads"
    reports_dir: str = "reports"
    max_upload_size_bytes: int = 10 * 1024 * 1024
    ollama_base_url: str = "http://localhost:11434"
    extraction_model: str = "smollm:360m"
    evaluation_model: str = "gemma3:1b-it-q4_K_M"
    decision_model: str = "phi4-mini:3.8b-q4_K_M"
    report_model: str = "gemma3:1b-it-q4_K_M"
    notification_model: str = "smollm:360m"
    resend_api_key: str = ""
    resend_from_email: str = "noreply@example.com"
    langchain_tracing_v2: bool = Field(default=False, alias="LANGCHAIN_TRACING_V2")
    langchain_api_key: str = Field(default="", alias="LANGCHAIN_API_KEY")
    langchain_project: str = Field(default="ctse-assignment2", alias="LANGCHAIN_PROJECT")
    retry_attempts: int = 2

    def ensure_dirs(self, root: Path) -> None:
        (root / self.uploads_dir).mkdir(parents=True, exist_ok=True)
        (root / self.reports_dir).mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    return Settings()

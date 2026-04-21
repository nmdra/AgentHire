"""Initialize local SQLite database for AgentHire."""

from __future__ import annotations

from app.config import get_settings
from app.database import init_database


if __name__ == "__main__":
    init_database(get_settings().db_path)
    print("Database initialized")

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI

from app.api.routes import router
from app.core.config import Settings, get_settings
from app.db.database import init_db


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="AgentHire Multi-Agent Application Analysis System")

    cfg = settings or get_settings()
    root = Path.cwd()
    cfg.ensure_dirs(root)
    init_db(cfg.db_path)

    app.include_router(router)
    return app


app = create_app()

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.api.routes import router
from app.core.config import Settings, get_settings
from app.tools.database import init_db


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


def create_app(settings: Settings | None = None) -> FastAPI:
    has_explicit_settings = settings is not None
    cfg = settings or get_settings()

    def initialize_storage() -> None:
        root = Path.cwd()
        cfg.ensure_dirs(root)
        init_db(cfg.db_path)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if not has_explicit_settings:
            initialize_storage()
        yield

    app = FastAPI(title="AgentHire Multi-Agent Application Analysis System", lifespan=lifespan)

    if has_explicit_settings:
        initialize_storage()
        app.dependency_overrides[get_settings] = lambda: cfg

    app.include_router(router)
    return app


app = create_app()

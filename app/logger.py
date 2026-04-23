"""Application logging configuration."""

from __future__ import annotations

import logging
import sys
from typing import Any

try:
    from loguru import logger as loguru_logger
except ImportError:  # pragma: no cover - optional dependency fallback
    loguru_logger = None

from app.config import get_settings


def configure_logging() -> None:
    """Configure loguru based on application settings."""
    settings = get_settings()

    log_level = "DEBUG" if settings.debug_logs else "INFO"

    if loguru_logger is not None:
        loguru_logger.remove()
        loguru_logger.add(
            sys.stdout,
            colorize=True,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            level=log_level,
            enqueue=True,
        )
        return

    logging.basicConfig(
        stream=sys.stdout,
        level=getattr(logging, log_level),
        format="%(asctime)s | %(levelname)-8s | %(name)s - %(message)s",
        force=True,
    )


# Pre-configure with default settings at import time
configure_logging()

def setup_logger(name: str) -> Any:
    """Return a logger bound with a specific component name."""
    if loguru_logger is not None:
        return loguru_logger.bind(component=name)
    return logging.getLogger(name)

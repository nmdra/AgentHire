"""Application logging configuration."""

from __future__ import annotations

import sys
from loguru import logger

from app.config import get_settings


def configure_logging() -> None:
    """Configure loguru based on application settings."""
    settings = get_settings()
    
    # Remove any pre-existing handlers
    logger.remove()
    
    # Configure structured logging level based on debug_logs setting
    log_level = "DEBUG" if settings.debug_logs else "INFO"
    
    # Add handler for standard output
    logger.add(
        sys.stdout,
        colorize=True,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=log_level,
        enqueue=True,
    )

# Pre-configure with default settings at import time
configure_logging()

def setup_logger(name: str) -> type[logger]:
    """Return a logger bound with a specific component name."""
    return logger.bind(component=name)

"""Configure loguru for JSON or text stderr output (Phase 66)."""

from __future__ import annotations

import os
import sys

from loguru import logger


def configure_logging() -> None:
    log_format = os.environ.get("LOG_FORMAT", "text").strip().lower()
    log_level = os.environ.get("LOG_LEVEL", "INFO").strip().upper()

    logger.remove()
    if log_format == "json":
        logger.add(sys.stderr, level=log_level, serialize=True)
    else:
        logger.add(
            sys.stderr,
            level=log_level,
            format="{time:ISO8601} | {level} | {name}:{function}:{line} | {message}",
        )

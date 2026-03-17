"""
Takone — Structured logging setup.

Logs go to a file to avoid interfering with the split-terminal TUI.
Enable with TAKONE_LOG_LEVEL=DEBUG (default: WARNING).

Usage:
    from .log import logger
    logger.debug("Processing shot %s", shot_id)
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

_LOG_DIR = Path(__file__).parent.parent / "logs"
_LOG_FILE = _LOG_DIR / "takone.log"

logger = logging.getLogger("takone")


def setup_logging() -> None:
    """Configure file-based logging. Safe to call multiple times."""
    if logger.handlers:
        return  # already configured

    level_name = os.getenv("TAKONE_LOG_LEVEL", "WARNING").upper()
    level = getattr(logging, level_name, logging.WARNING)
    logger.setLevel(level)

    # Only add file handler if debug logging is requested
    if level <= logging.DEBUG:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(_LOG_FILE, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(handler)
    else:
        logger.addHandler(logging.NullHandler())

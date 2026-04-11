from __future__ import annotations

import os
import sys
from pathlib import Path

from loguru import logger

from config.settings import get_settings


def configure_logger() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    settings = get_settings()
    settings.artifacts_logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = Path(settings.artifacts_logs_dir) / "app.log"

    logger.remove()
    logger.add(sys.stderr, level=level, backtrace=False, diagnose=False)
    logger.add(str(log_path), level=level, rotation="10 MB", retention="10 days", enqueue=True)


def get_logger():
    return logger

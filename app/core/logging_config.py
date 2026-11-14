"""Centralized logging configuration for the desktop application."""

from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path


def configure_logging(log_directory: Path | str | None = None) -> Path | None:
    """Configure root logging and optionally write rotating UTF-8 log files.

    The log directory can be supplied explicitly or through
    ``OCR_AUTOMATION_LOG_DIR``. No path is inferred from the current directory.
    """
    configured_directory = log_directory or os.environ.get("OCR_AUTOMATION_LOG_DIR")
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    resolved_directory: Path | None = None

    if configured_directory:
        resolved_directory = Path(configured_directory).expanduser()
        resolved_directory.mkdir(parents=True, exist_ok=True)
        handlers.append(
            logging.handlers.RotatingFileHandler(
                resolved_directory / "ocr_automation.log",
                maxBytes=5 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
        )

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=handlers,
        force=True,
    )
    return resolved_directory

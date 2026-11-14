from __future__ import annotations

import logging

from app.core.logging_config import configure_logging


def test_logging_config_creates_rotating_log_file(tmp_path) -> None:
    log_directory = tmp_path / "logs"
    configured = configure_logging(log_directory)
    logger = logging.getLogger("ocr-automation-test")
    logger.info("foundation log test")

    assert configured == log_directory
    assert (log_directory / "ocr_automation.log").exists()

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.bootstrap import (
    APPLICATION_NAME,
    APPLICATION_VERSION,
    ORGANIZATION_NAME,
    bootstrap_application,
)
from app.ui.application_window import ApplicationWindow


def test_bootstrap_creates_application_and_main_window() -> None:
    application, main_window = bootstrap_application(["ocr-automation-test"], authenticate=False)

    assert isinstance(application, QApplication)
    assert isinstance(main_window, ApplicationWindow)
    assert application.applicationName() == APPLICATION_NAME
    assert application.applicationVersion() == APPLICATION_VERSION
    assert application.organizationName() == ORGANIZATION_NAME


def test_bootstrap_reuses_existing_qapplication() -> None:
    first_application, first_window = bootstrap_application(["ocr-automation-test"], authenticate=False)
    second_application, second_window = bootstrap_application(["ignored"], authenticate=False)

    assert second_application is first_application
    assert isinstance(first_window, ApplicationWindow)
    assert isinstance(second_window, ApplicationWindow)
    assert second_window is not first_window

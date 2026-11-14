from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

from app.ui.application_window import ApplicationWindow
from app.ui.view_models.feature_catalog import FeatureSummary

_APP: QApplication | None = None


class FakeFeatureCatalog:
    def __init__(self, features: tuple[FeatureSummary, ...]) -> None:
        self.features = features

    def list_available(self) -> tuple[FeatureSummary, ...]:
        return self.features


class FakeWorkspaceFactory:
    def __init__(self) -> None:
        self.created_for: list[str] = []

    def create_workspace(self, feature_id: str, parent: QWidget) -> QWidget:
        self.created_for.append(feature_id)
        return QWidget(parent)


def _application() -> QApplication:
    global _APP
    application = QApplication.instance()
    if application is None:
        _APP = QApplication(["ocr-automation-ui-test"])
        application = _APP
    return application


def test_application_window_starts_with_dashboard_and_empty_feature_catalog() -> None:
    _application()
    window = ApplicationWindow()

    assert window.windowTitle() == "OCR Automation"
    assert window.pages.currentWidget() is window.dashboard_page
    assert window.dashboard_page.feature_grid.count() == 1
    assert window.header.title_label.text() == "Overview"

    window.navigate("settings")
    assert window.pages.currentWidget() is window.settings_page
    assert window.header.title_label.text() == "Settings"


def test_dashboard_and_sidebar_are_populated_from_feature_catalog() -> None:
    _application()
    feature = FeatureSummary(
        feature_id="tax_invoice",
        display_name="Tax Invoice Reader",
        description="Read tax invoice documents.",
        version="1.0.0",
    )
    window = ApplicationWindow(feature_catalog=FakeFeatureCatalog((feature,)))

    assert window.dashboard_page.feature_grid.count() == 1
    assert "tax_invoice" in window.sidebar._feature_buttons
    assert window.dashboard_page._feature_count_value.text() == "1"


def test_feature_workspace_is_created_lazily_and_reused() -> None:
    _application()
    feature = FeatureSummary("invoice_reader", "Invoice Reader", "Read invoices.", "1.0.0")
    factory = FakeWorkspaceFactory()
    window = ApplicationWindow(
        feature_catalog=FakeFeatureCatalog((feature,)),
        workspace_factory=factory,
    )

    window.open_feature("invoice_reader")
    first_page = window.pages.currentWidget()
    window.open_feature("invoice_reader")

    assert factory.created_for == ["invoice_reader"]
    assert window.pages.currentWidget() is first_page
    assert window.header.title_label.text() == "Invoice Reader"


def test_application_window_rejects_feature_not_in_current_catalog() -> None:
    _application()
    window = ApplicationWindow()

    initial_page = window.pages.currentWidget()
    window.open_feature("not_registered")

    assert window.pages.currentWidget() is initial_page
    assert not window._workspace_pages

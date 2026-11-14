"""Application navigation sidebar."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.ui.view_models.feature_catalog import FeatureSummary


class Sidebar(QFrame):
    navigation_requested = Signal(str)
    feature_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(244)
        self._navigation_buttons: dict[str, QPushButton] = {}
        self._feature_buttons: dict[str, QPushButton] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 22, 18, 18)
        layout.setSpacing(8)

        brand = QLabel("OCR AUTOMATION")
        brand.setObjectName("brandTitle")
        layout.addWidget(brand)
        caption = QLabel("DOCUMENT WORKSPACE")
        caption.setObjectName("brandCaption")
        layout.addWidget(caption)
        layout.addSpacing(28)

        self._add_section_label(layout, "WORKSPACE")
        self._add_navigation_button(layout, "dashboard", "Overview")
        layout.addSpacing(18)
        self._add_section_label(layout, "MANAGEMENT")
        self._add_navigation_button(layout, "feature_cms", "Feature Management")
        self._add_navigation_button(layout, "settings", "Settings")
        self._add_navigation_button(layout, "users", "User Management")

        layout.addSpacing(18)
        self._add_section_label(layout, "AVAILABLE FEATURES")
        self._feature_host = QWidget()
        self._feature_container = QVBoxLayout(self._feature_host)
        self._feature_container.setContentsMargins(0, 0, 0, 0)
        self._feature_container.setSpacing(6)
        self._feature_scroll = QScrollArea()
        self._feature_scroll.setWidgetResizable(True)
        self._feature_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._feature_scroll.setWidget(self._feature_host)
        layout.addWidget(self._feature_scroll, 1)
        layout.addStretch(1)

        footer = QLabel("OFFLINE-FIRST DESKTOP APP")
        footer.setObjectName("sidebarFooter")
        layout.addWidget(footer)
        self.set_active("dashboard")

    @staticmethod
    def _add_section_label(layout: QVBoxLayout, text: str) -> None:
        label = QLabel(text)
        label.setObjectName("sidebarSection")
        layout.addWidget(label)

    def _add_navigation_button(self, layout: QVBoxLayout, key: str, label: str) -> None:
        button = QPushButton(label)
        button.setObjectName("navigationButton")
        button.setProperty("navigationKey", key)
        button.setCheckable(True)
        button.clicked.connect(
            lambda _checked=False, item=key: self.navigation_requested.emit(item)
        )
        self._navigation_buttons[key] = button
        layout.addWidget(button)

    def set_page_visibility(self, visible_pages: frozenset[str]) -> None:
        for key, button in self._navigation_buttons.items():
            button.setVisible(key in visible_pages)

    def set_features(self, features: tuple[FeatureSummary, ...]) -> None:
        while self._feature_container.count():
            item = self._feature_container.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._feature_buttons.clear()

        for feature in features:
            button = QPushButton(feature.display_name)
            button.setObjectName("featureNavigationButton")
            button.setToolTip(feature.description)
            button.setProperty("featureId", feature.feature_id)
            button.setCheckable(True)
            button.clicked.connect(
                lambda _checked=False, feature_id=feature.feature_id:
                    self.feature_requested.emit(feature_id)
            )
            self._feature_buttons[feature.feature_id] = button
            self._feature_container.addWidget(button)

    def set_active(self, key: str) -> None:
        for button in self._navigation_buttons.values():
            button.setChecked(button.property("navigationKey") == key)
        for button in self._feature_buttons.values():
            button.setChecked(button.property("featureId") == key)

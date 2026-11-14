"""Dashboard page driven by the authorized feature catalog projection."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.ui.view_models.feature_catalog import FeatureSummary


class DashboardPage(QWidget):
    feature_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(30, 28, 30, 30)
        content_layout.setSpacing(22)

        intro = QVBoxLayout()
        eyebrow = QLabel("WORKSPACE OVERVIEW")
        eyebrow.setObjectName("eyebrow")
        heading = QLabel("Good to see you.")
        heading.setObjectName("heroTitle")
        description = QLabel(
            "Choose an available document feature to start a workflow. "
            "Your original files remain separate from generated outputs."
        )
        description.setObjectName("bodySecondary")
        description.setWordWrap(True)
        intro.addWidget(eyebrow)
        intro.addWidget(heading)
        intro.addWidget(description)
        content_layout.addLayout(intro)

        stats = QGridLayout()
        stats.setSpacing(14)
        self.feature_count, self._feature_count_value = self._create_stat_card(
            "AVAILABLE FEATURES", "0", "Ready for your account"
        )
        self.job_count, _ = self._create_stat_card(
            "PROCESSING JOBS", "—", "Job orchestration not connected"
        )
        self.output_count, _ = self._create_stat_card(
            "RECENT OUTPUTS", "—", "History service not connected"
        )
        stats.addWidget(self.feature_count, 0, 0)
        stats.addWidget(self.job_count, 0, 1)
        stats.addWidget(self.output_count, 0, 2)
        content_layout.addLayout(stats)

        section_header = QVBoxLayout()
        section_title = QLabel("Your features")
        section_title.setObjectName("sectionTitle")
        section_description = QLabel("Available tools are provided by the Feature Registry.")
        section_description.setObjectName("bodySecondary")
        section_header.addWidget(section_title)
        section_header.addWidget(section_description)
        content_layout.addLayout(section_header)

        self.feature_grid = QGridLayout()
        self.feature_grid.setSpacing(14)
        content_layout.addLayout(self.feature_grid)
        content_layout.addStretch(1)
        scroll_area.setWidget(content)
        root.addWidget(scroll_area)
        self.set_features(())

    @staticmethod
    def _create_stat_card(label: str, value: str, detail: str) -> tuple[QFrame, QLabel]:
        card = QFrame()
        card.setObjectName("statCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        name = QLabel(label)
        name.setObjectName("statLabel")
        number = QLabel(value)
        number.setObjectName("statValue")
        description = QLabel(detail)
        description.setObjectName("statDetail")
        layout.addWidget(name)
        layout.addWidget(number)
        layout.addWidget(description)
        return card, number

    def set_features(self, features: tuple[FeatureSummary, ...]) -> None:
        while self.feature_grid.count():
            item = self.feature_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self._feature_count_value.setText(str(len(features)))
        if not features:
            empty = QFrame()
            empty.setObjectName("emptyState")
            empty_layout = QVBoxLayout(empty)
            empty_layout.setContentsMargins(22, 24, 22, 24)
            title = QLabel("No features available yet")
            title.setObjectName("emptyTitle")
            message = QLabel(
                "The Feature Registry has not supplied any enabled features. "
                "Once a verified feature is registered, enabled, and authorized, "
                "it will appear here automatically."
            )
            message.setObjectName("bodySecondary")
            message.setWordWrap(True)
            empty_layout.addWidget(title)
            empty_layout.addWidget(message)
            self.feature_grid.addWidget(empty, 0, 0, 1, 3)
            return

        for index, feature in enumerate(features):
            card = QFrame()
            card.setObjectName("featureCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(18, 18, 18, 18)
            name = QLabel(feature.display_name)
            name.setObjectName("cardTitle")
            detail = QLabel(feature.description)
            detail.setObjectName("bodySecondary")
            detail.setWordWrap(True)
            version = QLabel(f"Version {feature.version}")
            version.setObjectName("statDetail")
            open_button = QPushButton("Open workspace")
            open_button.setObjectName("primaryButton")
            open_button.clicked.connect(
                lambda _checked=False, feature_id=feature.feature_id:
                    self.feature_selected.emit(feature_id)
            )
            card_layout.addWidget(name)
            card_layout.addWidget(detail)
            card_layout.addWidget(version)
            card_layout.addStretch(1)
            card_layout.addWidget(open_button)
            self.feature_grid.addWidget(card, index // 3, index % 3)

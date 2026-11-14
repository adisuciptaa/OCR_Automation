"""Application settings landing page."""

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class SettingsPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 28, 30, 30)
        layout.setSpacing(16)

        eyebrow = QLabel("PREFERENCES")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("Settings")
        title.setObjectName("heroTitle")
        description = QLabel("Application-level preferences and runtime information.")
        description.setObjectName("bodySecondary")
        layout.addWidget(eyebrow)
        layout.addWidget(title)
        layout.addWidget(description)

        card = QFrame()
        card.setObjectName("noticeCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        card_title = QLabel("Configuration foundation")
        card_title.setObjectName("cardTitle")
        card_text = QLabel(
            "The Core Configuration Manager is available. Editable preferences, "
            "validation schemas, and persistence controls will be added when their "
            "application-level settings contract is defined."
        )
        card_text.setObjectName("bodySecondary")
        card_text.setWordWrap(True)
        card_layout.addWidget(card_title)
        card_layout.addWidget(card_text)
        layout.addWidget(card)
        layout.addStretch(1)

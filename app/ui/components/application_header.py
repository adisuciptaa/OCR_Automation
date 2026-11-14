"""Context header displayed above application pages."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class ApplicationHeader(QFrame):
    sign_out_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("applicationHeader")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(30, 18, 30, 18)

        title_group = QVBoxLayout()
        self.title_label = QLabel("Overview")
        self.title_label.setObjectName("pageTitle")
        self.subtitle_label = QLabel("Your document processing workspace")
        self.subtitle_label.setObjectName("pageSubtitle")
        title_group.addWidget(self.title_label)
        title_group.addWidget(self.subtitle_label)
        layout.addLayout(title_group)
        layout.addStretch(1)

        self.user_label = QLabel("")
        self.user_label.setObjectName("signedInUser")
        layout.addWidget(self.user_label)
        self.sign_out_button = QPushButton("Sign out")
        self.sign_out_button.setObjectName("signOutButton")
        self.sign_out_button.clicked.connect(self.sign_out_requested.emit)
        self.sign_out_button.hide()
        layout.addWidget(self.sign_out_button)
        self.status_label = QLabel("CORE INITIALIZED")
        self.status_label.setObjectName("systemStatus")
        layout.addWidget(self.status_label)

    def set_user(self, display_name: str, username: str) -> None:
        self.user_label.setText(f"{display_name} · @{username}" if username else "")
        self.sign_out_button.setVisible(bool(username))

    def set_context(self, title: str, subtitle: str) -> None:
        self.title_label.setText(title)
        self.subtitle_label.setText(subtitle)

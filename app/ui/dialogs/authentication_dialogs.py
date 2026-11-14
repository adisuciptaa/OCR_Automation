"""First-run administrator setup and sign-in dialogs."""
from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QMessageBox,
    QVBoxLayout, QLabel, QWidget,
)

from app.core.exceptions import ApplicationError
from app.security.contracts import AuthenticationService
from app.security.models import UserIdentity

LOGGER = logging.getLogger(__name__)


class InitialAdministratorDialog(QDialog):
    def __init__(self, authentication: AuthenticationService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.authentication = authentication
        self.identity: UserIdentity | None = None
        self.setWindowTitle("Initial administrator setup")
        self.setModal(True)
        layout = QVBoxLayout(self)
        intro = QLabel("Create the first administrator account. No default password is configured.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = QFormLayout()
        self.username = QLineEdit()
        self.username.setPlaceholderText("e.g. admin")
        self.display_name = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_password = QLineEdit()
        self.confirm_password.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Username", self.username)
        form.addRow("Display name", self.display_name)
        form.addRow("Password", self.password)
        form.addRow("Confirm password", self.confirm_password)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._create)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _create(self) -> None:
        if self.password.text() != self.confirm_password.text():
            QMessageBox.warning(self, "Password mismatch", "The passwords do not match.")
            return
        try:
            self.identity = self.authentication.setup_initial_administrator(
                self.username.text(), self.display_name.text(), self.password.text()
            )
        except ApplicationError as exc:
            QMessageBox.warning(self, "Setup failed", exc.safe_message)
            return
        except Exception:
            LOGGER.exception("Initial administrator setup failed.")
            QMessageBox.warning(self, "Setup failed", "The account could not be created due to an internal error.")
            return
        self.accept()


class LoginDialog(QDialog):
    def __init__(self, authentication: AuthenticationService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.authentication = authentication
        self.identity: UserIdentity | None = None
        self.setWindowTitle("Sign in — OCR Automation")
        self.setModal(True)
        layout = QVBoxLayout(self)
        intro = QLabel("Sign in with your OCR Automation account.")
        layout.addWidget(intro)
        form = QFormLayout()
        self.username = QLineEdit()
        self.username.setPlaceholderText("Username")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Username", self.username)
        form.addRow("Password", self.password)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._login)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _login(self) -> None:
        try:
            self.identity = self.authentication.authenticate(self.username.text(), self.password.text())
        except ApplicationError as exc:
            QMessageBox.warning(self, "Sign-in failed", exc.safe_message)
            self.password.clear()
            self.password.setFocus()
            return
        except Exception:
            LOGGER.exception("Authentication request failed.")
            QMessageBox.warning(self, "Sign-in failed", "Sign-in is temporarily unavailable. Please try again.")
            self.password.clear()
            return
        self.accept()

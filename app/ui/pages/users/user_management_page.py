"""Administrative user management view; all mutations delegate to Core security services."""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.core.exceptions import ApplicationError
from app.security.contracts import UserAdministrationService

LOGGER = logging.getLogger(__name__)


class CreateUserDialog(QDialog):
    def __init__(self, roles: tuple[object, ...], parent: QWidget | None = None,
                 selected_role_ids: tuple[str, ...] = ()) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create user")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.username = QLineEdit()
        self.display_name = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm = QLineEdit()
        self.confirm.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Username", self.username)
        form.addRow("Display name", self.display_name)
        form.addRow("Password", self.password)
        form.addRow("Confirm password", self.confirm)
        layout.addLayout(form)
        layout.addWidget(QLabel("Assign roles"))
        self.role_list = QListWidget()
        for role in roles:
            item = QListWidgetItem(role.name)
            item.setData(Qt.ItemDataRole.UserRole, role.role_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if role.role_id in selected_role_ids else Qt.CheckState.Unchecked)
            self.role_list.addItem(item)
        layout.addWidget(self.role_list)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[str, str, str, tuple[str, ...]]:
        selected = tuple(self.role_list.item(i).data(Qt.ItemDataRole.UserRole)
                         for i in range(self.role_list.count())
                         if self.role_list.item(i).checkState() == Qt.CheckState.Checked)
        return self.username.text(), self.display_name.text(), self.password.text(), selected


class UserManagementPage(QWidget):
    def __init__(self, authentication: UserAdministrationService, actor_id: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.authentication = authentication
        self.actor_id = actor_id
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 28, 30, 30)
        title = QLabel("User Management")
        title.setObjectName("heroTitle")
        description = QLabel("Create accounts, assign roles, and disable access when required.")
        description.setObjectName("bodySecondary")
        layout.addWidget(title)
        layout.addWidget(description)
        actions = QHBoxLayout()
        self.create_button = QPushButton("Create user")
        self.create_button.setObjectName("primaryButton")
        self.create_button.clicked.connect(self.create_user)
        self.edit_roles_button = QPushButton("Edit selected roles")
        self.edit_roles_button.clicked.connect(self.edit_roles)
        self.toggle_button = QPushButton("Activate / deactivate selected")
        self.toggle_button.clicked.connect(self.toggle_selected)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        actions.addWidget(self.create_button)
        actions.addWidget(self.edit_roles_button)
        actions.addWidget(self.toggle_button)
        actions.addWidget(refresh)
        actions.addStretch(1)
        layout.addLayout(actions)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Username", "Display name", "Roles", "Status", "Last login"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)
        self.refresh()

    def refresh(self) -> None:
        self.table.setRowCount(0)
        try:
            users = self.authentication.list_users(self.actor_id)
        except ApplicationError as exc:
            QMessageBox.warning(self, "Access denied", exc.safe_message)
            return
        except Exception:
            LOGGER.exception("Unable to refresh the user list.")
            QMessageBox.warning(self, "Unable to load users", "The user list is temporarily unavailable.")
            return
        self.table.setRowCount(len(users))
        for row, user in enumerate(users):
            values = (user.username, user.display_name, ", ".join(user.roles),
                      "Active" if user.is_active else "Inactive",
                      user.last_login_at.astimezone().strftime("%Y-%m-%d %H:%M") if user.last_login_at else "Never")
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
            self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, user.user_id)

    def create_user(self) -> None:
        try:
            roles = self.authentication.list_roles(self.actor_id)
            dialog = CreateUserDialog(roles, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            username, display_name, password, role_ids = dialog.values()
            if password != dialog.confirm.text():
                QMessageBox.warning(self, "Password mismatch", "The passwords do not match.")
                return
            self.authentication.create_user(self.actor_id, username, display_name, password, role_ids)
            self.refresh()
        except ApplicationError as exc:
            QMessageBox.warning(self, "Unable to create user", exc.safe_message)
        except Exception:
            LOGGER.exception("User creation failed.")
            QMessageBox.warning(self, "Unable to create user", "An internal error prevented user creation.")

    def edit_roles(self) -> None:
        selected = self._selected_user_id()
        if selected is None:
            QMessageBox.information(self, "Select a user", "Select a user row first.")
            return
        try:
            roles = self.authentication.list_roles(self.actor_id)
            current_roles = self.authentication.get_user_role_ids(self.actor_id, selected)
            dialog = CreateUserDialog(roles, self, current_roles)
            dialog.setWindowTitle("Edit user roles")
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            _, _, _, role_ids = dialog.values()
            self.authentication.update_user_roles(self.actor_id, selected, role_ids)
            self.refresh()
        except ApplicationError as exc:
            QMessageBox.warning(self, "Unable to update roles", exc.safe_message)
        except Exception:
            LOGGER.exception("User role update failed.")
            QMessageBox.warning(self, "Unable to update roles", "An internal error prevented the role update.")

    def _selected_user_id(self) -> str | None:
        row = self.table.currentRow()
        if row < 0 or self.table.item(row, 0) is None:
            return None
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def toggle_selected(self) -> None:
        row = self.table.currentRow()
        user_id = self._selected_user_id()
        if user_id is None:
            QMessageBox.information(self, "Select a user", "Select a user row first.")
            return
        currently_active = self.table.item(row, 3).text() == "Active"
        try:
            self.authentication.set_user_active(self.actor_id, user_id, not currently_active)
            self.refresh()
        except ApplicationError as exc:
            QMessageBox.warning(self, "Unable to update user", exc.safe_message)
        except Exception:
            LOGGER.exception("User activation update failed.")
            QMessageBox.warning(self, "Unable to update user", "An internal error prevented the account update.")

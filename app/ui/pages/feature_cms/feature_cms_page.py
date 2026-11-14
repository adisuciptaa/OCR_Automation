"""Feature Registry overview; mutations remain application-service operations."""
from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from app.feature_manager.models import FeatureRecord, FeatureState
from app.feature_manager.contracts import FeatureConfigurationManager
from app.security.contracts import AuthorizationService
from app.ui.pages.feature_cms.feature_configuration_dialog import FeatureConfigurationDialog
from app.ui.view_models.feature_management import FeatureManagementProvider

LOGGER = logging.getLogger(__name__)


class FeatureCmsPage(QWidget):
    def __init__(
        self,
        provider: FeatureManagementProvider | None = None,
        *,
        configuration_manager: FeatureConfigurationManager | None = None,
        authorization: AuthorizationService | None = None,
        actor_id: str | None = None,
        feature_manager: object | None = None,
        publisher_trust_manager: object | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._provider = provider
        self._configuration_manager = configuration_manager
        self._authorization = authorization
        self._actor_id = actor_id
        self._feature_manager = feature_manager
        self._publisher_trust_manager = publisher_trust_manager
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 28, 30, 30)
        layout.setSpacing(16)

        eyebrow = QLabel("ADMINISTRATION")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("Feature Management")
        title.setObjectName("heroTitle")
        description = QLabel(
            "Review installed business capabilities and their lifecycle state. "
            "Package operations are handled by the Core Feature Manager."
        )
        description.setObjectName("bodySecondary")
        description.setWordWrap(True)
        layout.addWidget(eyebrow)
        layout.addWidget(title)
        layout.addWidget(description)
        refresh_button = QPushButton("Refresh registry")
        refresh_button.setObjectName("primaryButton")
        refresh_button.clicked.connect(self.refresh_records)
        actions = QHBoxLayout()
        actions.addWidget(refresh_button)
        self.trust_publisher_button = QPushButton("Trust publisher")
        self.trust_publisher_button.setObjectName("secondaryButton")
        self.trust_publisher_button.clicked.connect(self.register_publisher)
        self.install_package_button = QPushButton("Install feature package")
        self.install_package_button.setObjectName("primaryButton")
        self.install_package_button.clicked.connect(self.install_package)
        can_trust = bool(
            authorization is not None and actor_id
            and authorization.is_allowed(actor_id, "publisher.manage")
            and publisher_trust_manager is not None
        )
        can_install = bool(
            authorization is not None and actor_id
            and authorization.is_allowed(actor_id, "feature.install")
            and feature_manager is not None
        )
        self.trust_publisher_button.setVisible(can_trust)
        self.install_package_button.setVisible(can_install)
        actions.addWidget(self.trust_publisher_button)
        actions.addWidget(self.install_package_button)
        layout.addLayout(actions)

        self.records_container = QFrame()
        self.records_container.setObjectName("noticeCard")
        self.records_layout = QVBoxLayout(self.records_container)
        self.records_layout.setContentsMargins(20, 18, 20, 18)
        self.records_layout.setSpacing(12)
        layout.addWidget(self.records_container)
        layout.addStretch(1)
        self.refresh_records()

    def refresh_records(self) -> None:
        while self.records_layout.count():
            item = self.records_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        heading = QLabel("Installed feature registry")
        heading.setObjectName("cardTitle")
        self.records_layout.addWidget(heading)
        records: tuple[FeatureRecord, ...] = ()
        registry_load_failed = False
        if self._provider is not None:
            try:
                records = self._provider.list_records()
            except Exception:
                registry_load_failed = True
                LOGGER.exception("Unable to load Feature Registry records.")
        if registry_load_failed:
            message = QLabel(
                "Feature Registry could not be loaded. Check application logs and verify "
                "that the current account has the feature.registry.view permission."
            )
            message.setObjectName("bodySecondary")
            message.setWordWrap(True)
            self.records_layout.addWidget(message)
            return
        if not records:
            message = QLabel(
                "No feature packages are registered. Packages must pass manifest, "
                "compatibility, dependency, and trusted-digest validation before registration."
            )
            message.setObjectName("bodySecondary")
            message.setWordWrap(True)
            self.records_layout.addWidget(message)
            return
        for record in records:
            row = QFrame()
            row_layout = QGridLayout(row)
            name = QLabel(record.manifest.display_name)
            name.setObjectName("cardTitle")
            identity = QLabel(f"{record.feature_id} · v{record.manifest.version}")
            identity.setObjectName("bodySecondary")
            state = QLabel(record.state.value.replace("_", " ").title())
            state.setObjectName("statDetail")
            row_layout.addWidget(name, 0, 0)
            row_layout.addWidget(identity, 1, 0)
            row_layout.addWidget(state, 0, 1)
            if record.state is FeatureState.REGISTERED and self._can_manage_feature(record):
                enable_button = QPushButton("Enable")
                enable_button.setObjectName("primaryButton")
                enable_button.clicked.connect(
                    lambda _checked=False, item=record: self.enable_feature(item)
                )
                row_layout.addWidget(enable_button, 0, 2)
            if self._can_configure(record):
                configure_button = QPushButton("Configure")
                configure_button.setObjectName("primaryButton")
                configure_button.clicked.connect(
                    lambda _checked=False, item=record:
                        self.open_configuration(item)
                )
                row_layout.addWidget(configure_button, 0, 3)
            if self._can_uninstall(record):
                uninstall_button = QPushButton("Uninstall")
                uninstall_button.setObjectName("secondaryButton")
                uninstall_button.clicked.connect(
                    lambda _checked=False, item=record: self.uninstall_feature(item)
                )
                row_layout.addWidget(uninstall_button, 0, 4)
            self.records_layout.addWidget(row)


    def register_publisher(self) -> None:
        if self._publisher_trust_manager is None or not self._actor_id:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Register trusted publisher")
        dialog.setMinimumWidth(520)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Publisher ID (lowercase snake_case)"))
        publisher_id = QLineEdit("ocr_automation_dev")
        layout.addWidget(publisher_id)
        layout.addWidget(QLabel("Publisher display name (must match package manifest)"))
        display_name = QLineEdit("OCR Automation")
        layout.addWidget(display_name)
        layout.addWidget(QLabel("Ed25519 public key (Base64)"))
        public_key = QTextEdit()
        public_key.setPlaceholderText("Paste the Base64 public key generated by the local package tool")
        public_key.setMaximumHeight(100)
        layout.addWidget(public_key)
        buttons = QHBoxLayout()
        submit = QPushButton("Register publisher")
        cancel = QPushButton("Cancel")
        submit.clicked.connect(dialog.accept)
        cancel.clicked.connect(dialog.reject)
        buttons.addWidget(submit)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self._publisher_trust_manager.register_publisher(
                publisher_id.text().strip(), display_name.text().strip(),
                public_key.toPlainText().strip(), self._actor_id,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Publisher registration failed", str(exc))
            return
        QMessageBox.information(
            self, "Publisher trusted",
            "The publisher key is now trusted on this computer. Keep its private key offline.",
        )

    def install_package(self) -> None:
        if self._feature_manager is None or not self._actor_id:
            return
        archive, _ = QFileDialog.getOpenFileName(
            self, "Select signed feature package", "", "Feature packages (*.zip)"
        )
        if not archive:
            return
        try:
            record = self._feature_manager.install_archive(archive, self._actor_id)
        except Exception as exc:
            QMessageBox.critical(self, "Feature installation failed", str(exc))
            return
        self.refresh_records()
        QMessageBox.information(
            self, "Feature package installed",
            f"{record.manifest.display_name} ({record.feature_id}) was registered. Enable it to open its workspace.",
        )

    def _can_uninstall(self, record: FeatureRecord) -> bool:
        return bool(
            self._feature_manager is not None
            and self._actor_id
            and record.state in {FeatureState.REGISTERED, FeatureState.DISABLED, FeatureState.ERROR}
            and self._authorization is not None
            and self._authorization.is_allowed(self._actor_id, "feature.uninstall")
        )

    def uninstall_feature(self, record: FeatureRecord) -> None:
        if self._feature_manager is None or not self._actor_id:
            return
        confirmation = QMessageBox.question(
            self,
            "Uninstall feature",
            f"Uninstall {record.manifest.display_name}? The installed package will be moved "
            "to the feature backup area. You can install it again later.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return
        try:
            self._feature_manager.uninstall(record.feature_id, self._actor_id)
        except Exception as exc:
            QMessageBox.critical(self, "Feature uninstall failed", str(exc))
            return
        self.refresh_records()
        window = self.window()
        refresh = getattr(window, "refresh_features", None)
        if callable(refresh):
            refresh()
        QMessageBox.information(
            self,
            "Feature uninstalled",
            f"{record.manifest.display_name} was uninstalled. Its package was retained in backups.",
        )

    def enable_feature(self, record: FeatureRecord) -> None:
        if self._feature_manager is None or not self._actor_id:
            return
        try:
            self._feature_manager.enable(record.feature_id, self._actor_id)
        except Exception as exc:
            QMessageBox.critical(self, "Feature activation failed", str(exc))
            return
        self.refresh_records()
        window = self.window()
        refresh = getattr(window, "refresh_features", None)
        if callable(refresh):
            refresh()
        QMessageBox.information(
            self, "Feature enabled",
            f"{record.manifest.display_name} is enabled and available from the dashboard.",
        )

    def _can_configure(self, record: FeatureRecord) -> bool:
        if (
            self._configuration_manager is None
            or record.state not in {
                FeatureState.REGISTERED, FeatureState.ENABLED, FeatureState.DISABLED,
            }
        ):
            return False
        return self._can_manage_feature(record)

    def _can_manage_feature(self, record: FeatureRecord) -> bool:
        return bool(
            self._authorization is not None
            and self._actor_id
            and self._authorization.is_allowed(
                self._actor_id, f"feature.configure.{record.feature_id}"
            )
        )

    def open_configuration(self, record: FeatureRecord) -> None:
        if not self._can_configure(record):
            return
        dialog = FeatureConfigurationDialog(
            feature_id=record.feature_id,
            display_name=record.manifest.display_name,
            actor_id=self._actor_id or "",
            manager=self._configuration_manager,  # type: ignore[arg-type]
            parent=self,
        )
        dialog.exec()

"""Schema-driven editor for feature-owned configuration profiles."""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton,
    QSpinBox, QVBoxLayout, QWidget,
)

from app.core.exceptions import ApplicationError
from app.feature_manager.contracts import FeatureConfigurationManager
from app.feature_manager.models import ConfigurationScope


_SCOPE_LABELS = {
    ConfigurationScope.INSTALLATION: "Installation",
    ConfigurationScope.COMPANY: "Company",
    ConfigurationScope.USER: "User",
    ConfigurationScope.JOB: "Job",
}


class FeatureConfigurationDialog(QDialog):
    """Builds editable controls from a verified feature configuration schema."""

    def __init__(
        self,
        *,
        feature_id: str,
        display_name: str,
        actor_id: str,
        manager: FeatureConfigurationManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._feature_id = feature_id
        self._display_name = display_name
        self._actor_id = actor_id
        self._manager = manager
        self._schema: Mapping[str, Any] = {}
        self._controls: dict[str, QWidget] = {}

        self.setWindowTitle(f"Configure {display_name}")
        self.setMinimumSize(620, 560)
        root = QVBoxLayout(self)
        heading = QLabel(f"{display_name} configuration")
        heading.setObjectName("heroTitle")
        heading.setWordWrap(True)
        root.addWidget(heading)
        description = QLabel(
            "Edit the selected configuration scope. Values are validated by Feature Manager "
            "before they are persisted."
        )
        description.setObjectName("bodySecondary")
        description.setWordWrap(True)
        root.addWidget(description)

        scope_row = QHBoxLayout()
        self.scope_combo = QComboBox()
        for scope, label in _SCOPE_LABELS.items():
            self.scope_combo.addItem(label, scope.value)
        self.scope_key = QLineEdit("default")
        self.scope_key.setPlaceholderText("Scope identifier")
        self.load_button = QPushButton("Load")
        scope_row.addWidget(QLabel("Scope"))
        scope_row.addWidget(self.scope_combo)
        scope_row.addWidget(QLabel("Scope key"))
        scope_row.addWidget(self.scope_key, 1)
        scope_row.addWidget(self.load_button)
        root.addLayout(scope_row)

        self.schema_description = QLabel()
        self.schema_description.setObjectName("bodySecondary")
        self.schema_description.setWordWrap(True)
        root.addWidget(self.schema_description)

        self.form_host = QWidget()
        self.form = QFormLayout(self.form_host)
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        root.addWidget(self.form_host, 1)

        self.status_label = QLabel()
        self.status_label.setObjectName("bodySecondary")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        actions = QHBoxLayout()
        self.reset_button = QPushButton("Reset to defaults")
        self.save_button = QPushButton("Save configuration")
        self.save_button.setObjectName("primaryButton")
        self.close_button = QPushButton("Close")
        actions.addWidget(self.reset_button)
        actions.addStretch(1)
        actions.addWidget(self.close_button)
        actions.addWidget(self.save_button)
        root.addLayout(actions)

        self.scope_combo.currentIndexChanged.connect(self._scope_changed)
        self.load_button.clicked.connect(self.load_configuration)
        self.save_button.clicked.connect(self.save_configuration)
        self.reset_button.clicked.connect(self.reset_configuration)
        self.close_button.clicked.connect(self.reject)
        self._scope_changed()
        self.load_configuration()

    @property
    def _scope(self) -> ConfigurationScope:
        return ConfigurationScope(self.scope_combo.currentData())

    def _scope_changed(self) -> None:
        if self._scope is ConfigurationScope.INSTALLATION:
            self.scope_key.setText("default")
            self.scope_key.setEnabled(False)
        else:
            self.scope_key.setEnabled(True)
            self.scope_key.setText(
                self._actor_id if self._scope is ConfigurationScope.USER else ""
            )

    def load_configuration(self) -> None:
        key = self.scope_key.text().strip()
        if self._scope is ConfigurationScope.INSTALLATION:
            key = "default"
            self.scope_key.setText(key)
        try:
            schema = self._manager.get_configuration_schema(self._feature_id, self._actor_id)
            configuration = self._manager.get_configuration(
                self._feature_id, self._actor_id, self._scope, key
            )
        except ApplicationError as exc:
            self._show_error(exc.safe_message)
            return
        except (OSError, ValueError, TypeError):
            self._show_error("The configuration could not be loaded.")
            return

        self._schema = schema.definition
        self.schema_description.setText(str(self._schema.get("description", "")))
        self._rebuild_fields(dict(configuration.values))
        self.status_label.setText(
            f"Schema version {configuration.schema_version} · "
            f"Last updated by {configuration.updated_by}"
        )

    def _rebuild_fields(self, values: dict[str, Any]) -> None:
        while self.form.rowCount():
            self.form.removeRow(0)
        self._controls.clear()
        properties = self._schema.get("properties", {})
        required = set(self._schema.get("required", []))
        for name, definition in properties.items():
            value = values.get(name, definition.get("default"))
            label = str(definition.get("title") or name.replace("_", " ").title())
            if name in required:
                label += " *"
            description = str(definition.get("description", ""))
            control = self._create_control(name, definition, value)
            if description:
                control.setToolTip(description)
            self._controls[name] = control
            self.form.addRow(label, control)
        if not properties:
            self.form.addRow(QLabel("This feature has no editable configuration properties."))

    @staticmethod
    def _create_control(name: str, definition: Mapping[str, Any], value: Any) -> QWidget:
        enum_values = definition.get("enum")
        if isinstance(enum_values, list):
            combo = QComboBox()
            for option in enum_values:
                encoded = json.dumps(option, ensure_ascii=False)
                combo.addItem(str(option), encoded)
            selected = json.dumps(value, ensure_ascii=False)
            index = combo.findData(selected)
            if index >= 0:
                combo.setCurrentIndex(index)
            return combo

        declared_type = definition.get("type", "string")
        if isinstance(declared_type, list):
            declared_type = next((item for item in declared_type if item != "null"), "string")
        if declared_type == "boolean":
            checkbox = QCheckBox()
            checkbox.setChecked(bool(value))
            return checkbox
        if declared_type == "integer":
            spin = QSpinBox()
            spin.setRange(
                int(definition.get("minimum", -2_000_000_000)),
                int(definition.get("maximum", 2_000_000_000)),
            )
            if value is not None:
                spin.setValue(int(value))
            return spin
        if declared_type == "number":
            spin = QDoubleSpinBox()
            spin.setDecimals(6)
            spin.setRange(
                float(definition.get("minimum", -1_000_000_000)),
                float(definition.get("maximum", 1_000_000_000)),
            )
            if value is not None:
                spin.setValue(float(value))
            return spin
        if declared_type == "string":
            line = QLineEdit("" if value is None else str(value))
            line.setMaxLength(int(definition.get("maxLength", 32767)))
            return line

        editor = QPlainTextEdit()
        editor.setPlaceholderText(f"Enter {declared_type} value as JSON")
        editor.setPlainText(json.dumps(value, ensure_ascii=False, indent=2) if value is not None else "null")
        editor.setMaximumHeight(110)
        return editor

    def _collect_values(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for name, control in self._controls.items():
            if isinstance(control, QComboBox):
                encoded = control.currentData()
                values[name] = json.loads(encoded)
            elif isinstance(control, QCheckBox):
                values[name] = control.isChecked()
            elif isinstance(control, QSpinBox):
                values[name] = control.value()
            elif isinstance(control, QDoubleSpinBox):
                values[name] = control.value()
            elif isinstance(control, QLineEdit):
                values[name] = control.text()
            elif isinstance(control, QPlainTextEdit):
                try:
                    values[name] = json.loads(control.toPlainText())
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{name}: enter a valid JSON value.") from exc
        return values

    def save_configuration(self) -> None:
        try:
            values = self._collect_values()
            result = self._manager.save_configuration(
                self._feature_id, self._actor_id, self._scope,
                self.scope_key.text().strip(), values,
            )
        except ValueError as exc:
            self._show_error(str(exc))
            return
        except ApplicationError as exc:
            details = exc.details.get("validation_errors", [])
            message = exc.safe_message
            if details:
                message += "\\n" + "\\n".join(str(item) for item in details)
            self._show_error(message)
            return
        self.status_label.setText(f"Saved successfully · schema version {result.schema_version}")
        QMessageBox.information(self, "Configuration saved", "Feature configuration was saved.")

    def reset_configuration(self) -> None:
        answer = QMessageBox.question(
            self, "Reset configuration",
            "Remove this scope's saved overrides and restore schema defaults?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            result = self._manager.reset_configuration(
                self._feature_id, self._actor_id, self._scope, self.scope_key.text().strip()
            )
        except ApplicationError as exc:
            self._show_error(exc.safe_message)
            return
        self._rebuild_fields(dict(result.values))
        self.status_label.setText("Configuration reset to feature defaults.")
        QMessageBox.information(self, "Configuration reset", "Default configuration is now active.")

    def _show_error(self, message: str) -> None:
        self.status_label.setText(message)
        QMessageBox.warning(self, "Configuration", message)

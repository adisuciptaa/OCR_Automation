from __future__ import annotations

import os
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from datetime import UTC, datetime
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QSpinBox

from app.feature_manager.models import (
    ConfigurationScope, FeatureConfiguration, FeatureConfigurationSchema,
)
from app.ui.pages.feature_cms.feature_configuration_dialog import FeatureConfigurationDialog

_APP = None


class FakeConfigurationManager:
    def __init__(self):
        self.saved = []
        self.reset_calls = []
        self.values = {"language": "id", "dpi": 300, "enabled": True}

    def get_configuration_schema(self, feature_id, actor_id):
        return FeatureConfigurationSchema(feature_id, 1, {
            "type": "object",
            "title": "Sample settings",
            "description": "Configure sample processing.",
            "properties": {
                "language": {"type": "string", "enum": ["id", "en"], "default": "id"},
                "dpi": {"type": "integer", "minimum": 100, "maximum": 600, "default": 300},
                "enabled": {"type": "boolean", "default": True},
            },
            "required": ["language", "dpi", "enabled"],
        })

    def get_configuration(self, feature_id, actor_id, scope, scope_key):
        now = datetime.now(UTC)
        return FeatureConfiguration(feature_id, scope, scope_key, 1, self.values, now, now, actor_id)

    def save_configuration(self, feature_id, actor_id, scope, scope_key, values):
        self.saved.append((feature_id, actor_id, scope, scope_key, values))
        self.values = values
        return self.get_configuration(feature_id, actor_id, scope, scope_key)

    def reset_configuration(self, feature_id, actor_id, scope, scope_key):
        self.reset_calls.append((feature_id, actor_id, scope, scope_key))
        self.values = {"language": "id", "dpi": 300, "enabled": True}
        return self.get_configuration(feature_id, actor_id, scope, scope_key)


def _app():
    global _APP
    app = QApplication.instance()
    if app is None:
        _APP = QApplication(["feature-configuration-ui-test"])
        app = _APP
    return app


def test_configuration_dialog_builds_controls_from_schema():
    _app()
    manager = FakeConfigurationManager()
    dialog = FeatureConfigurationDialog(
        feature_id="sample_reader", display_name="Sample Reader",
        actor_id="admin", manager=manager,
    )
    assert isinstance(dialog._controls["language"], QComboBox)
    assert isinstance(dialog._controls["dpi"], QSpinBox)
    assert isinstance(dialog._controls["enabled"], QCheckBox)
    assert dialog._controls["dpi"].value() == 300


def test_configuration_dialog_saves_typed_values(monkeypatch):
    _app()
    manager = FakeConfigurationManager()
    dialog = FeatureConfigurationDialog(
        feature_id="sample_reader", display_name="Sample Reader",
        actor_id="admin", manager=manager,
    )
    dialog._controls["dpi"].setValue(450)
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    dialog.save_configuration()
    assert manager.saved[0][0:4] == (
        "sample_reader", "admin", ConfigurationScope.INSTALLATION, "default"
    )
    assert manager.saved[0][4]["dpi"] == 450


def test_configuration_dialog_changes_scope_key_for_user_scope():
    _app()
    dialog = FeatureConfigurationDialog(
        feature_id="sample_reader", display_name="Sample Reader",
        actor_id="user-42", manager=FakeConfigurationManager(),
    )
    dialog.scope_combo.setCurrentIndex(dialog.scope_combo.findData(ConfigurationScope.USER.value))
    assert dialog.scope_key.text() == "user-42"

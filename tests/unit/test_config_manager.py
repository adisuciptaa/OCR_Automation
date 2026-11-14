from __future__ import annotations

import json

import pytest

from app.core.config_manager import ConfigManager
from app.core.exceptions import ConfigurationError


def test_config_manager_loads_defaults_when_file_is_missing(tmp_path) -> None:
    manager = ConfigManager(
        tmp_path / "config.json",
        defaults={"application": {"log_level": "INFO"}},
    )
    assert manager.load() == {"application": {"log_level": "INFO"}}


def test_config_manager_deep_merges_loaded_values(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"application": {"theme": "dark"}}), encoding="utf-8")
    manager = ConfigManager(
        path,
        defaults={"application": {"theme": "system", "log_level": "INFO"}},
    )
    assert manager.load() == {
        "application": {"theme": "dark", "log_level": "INFO"}
    }


def test_config_manager_saves_atomically_and_round_trips(tmp_path) -> None:
    path = tmp_path / "nested" / "config.json"
    manager = ConfigManager(path, defaults={"enabled": True})
    manager.load()
    manager.update({"language": "id"})
    manager.save()
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "enabled": True, "language": "id"
    }
    assert not list(path.parent.glob("*.tmp"))


def test_config_manager_rejects_non_object_json(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text("[]", encoding="utf-8")
    manager = ConfigManager(path)
    with pytest.raises(ConfigurationError) as error:
        manager.load()
    assert error.value.code == "CONFIGURATION_INVALID"


def test_config_manager_returns_defensive_copy() -> None:
    manager = ConfigManager(defaults={"nested": {"value": 1}})
    returned = manager.values
    returned["nested"]["value"] = 9
    assert manager.values["nested"]["value"] == 1

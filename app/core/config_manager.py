"""JSON-backed application configuration management."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.core.exceptions import ConfigurationError


def _deep_merge(base: dict[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


class ConfigManager:
    """Loads, validates at the structural boundary, and atomically saves JSON config.

    Feature-specific schemas remain owned by their feature modules. This manager
    only guarantees that the application-level configuration is a JSON object.
    """

    def __init__(
        self,
        config_path: Path | str | None = None,
        *,
        defaults: Mapping[str, Any] | None = None,
    ) -> None:
        self._config_path = Path(config_path).expanduser() if config_path else None
        self._defaults = deepcopy(dict(defaults or {}))
        self._values: dict[str, Any] = deepcopy(self._defaults)

    @property
    def config_path(self) -> Path | None:
        return self._config_path

    @property
    def values(self) -> dict[str, Any]:
        return deepcopy(self._values)

    def load(self) -> dict[str, Any]:
        if self._config_path is None or not self._config_path.exists():
            self._values = deepcopy(self._defaults)
            return self.values

        try:
            with self._config_path.open("r", encoding="utf-8") as stream:
                loaded = json.load(stream)
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigurationError(
                "CONFIGURATION_LOAD_FAILED",
                "Application configuration could not be read.",
                details={"path": str(self._config_path), "reason": type(exc).__name__},
            ) from exc

        if not isinstance(loaded, dict):
            raise ConfigurationError(
                "CONFIGURATION_INVALID",
                "Application configuration must contain a JSON object.",
                details={"path": str(self._config_path)},
            )

        self._values = _deep_merge(self._defaults, loaded)
        return self.values

    def update(self, values: Mapping[str, Any]) -> dict[str, Any]:
        self._values = _deep_merge(self._values, values)
        return self.values

    def save(self) -> None:
        if self._config_path is None:
            raise ConfigurationError(
                "CONFIGURATION_PATH_UNSET",
                "A configuration file path is required before saving.",
            )

        parent = self._config_path.parent
        try:
            parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{self._config_path.name}.",
                suffix=".tmp",
                dir=parent,
            )
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                    json.dump(self._values, stream, ensure_ascii=False, indent=2)
                    stream.write("\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary_name, self._config_path)
            except Exception:
                try:
                    os.unlink(temporary_name)
                except FileNotFoundError:
                    pass
                raise
        except OSError as exc:
            raise ConfigurationError(
                "CONFIGURATION_SAVE_FAILED",
                "Application configuration could not be saved.",
                details={"path": str(self._config_path), "reason": type(exc).__name__},
            ) from exc

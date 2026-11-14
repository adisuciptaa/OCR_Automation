"""Presentation-facing feature catalog models and extension protocols."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from PySide6.QtWidgets import QWidget


@dataclass(frozen=True, slots=True)
class FeatureSummary:
    """Safe, display-only metadata projected from an authorized feature descriptor."""

    feature_id: str
    display_name: str
    description: str
    version: str
    icon: str = "document"

    def __post_init__(self) -> None:
        if not self.feature_id.strip():
            raise ValueError("feature_id must not be blank")
        if not self.display_name.strip():
            raise ValueError("display_name must not be blank")


class FeatureCatalogProvider(Protocol):
    """Read-only UI projection supplied by the application composition layer."""

    def list_available(self) -> tuple[FeatureSummary, ...]: ...


class FeatureWorkspaceFactory(Protocol):
    """Presentation adapter that delegates workspace creation to a feature module."""

    def create_workspace(self, feature_id: str, parent: QWidget) -> QWidget: ...


class RegistryFeatureCatalogProvider:
    """Projects only currently enabled and authorized registry features to the UI."""
    def __init__(self, feature_manager: object, user_id: str = "local") -> None:
        self._manager = feature_manager
        self._user_id = user_id

    def list_available(self) -> tuple[FeatureSummary, ...]:
        descriptors = self._manager.list_available(self._user_id)
        return tuple(FeatureSummary(item.feature_id, item.display_name, item.description,
                                    item.version, item.icon) for item in descriptors)

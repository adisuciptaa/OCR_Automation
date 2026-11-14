"""Presentation adapter connecting feature runtime workspaces to PySide6."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget

from app.core.event_bus import EventBus
from app.feature_manager.runtime import FeatureRuntimeManager


class FeatureRuntimeWorkspaceFactory(QObject):
    """Creates QWidget workspaces and relays runtime unloads to the GUI thread."""

    feature_unloaded = Signal(str)

    def __init__(
        self, runtime: FeatureRuntimeManager, actor_id: str, event_bus: EventBus
    ) -> None:
        super().__init__()
        self._runtime = runtime
        self._actor_id = actor_id
        self._unsubscribe = tuple(
            event_bus.subscribe(name, self._on_lifecycle_event)
            for name in ("feature.disabled", "feature.updated", "feature.uninstalled")
        )

    def create_workspace(self, feature_id: str, parent: QWidget) -> QWidget:
        workspace = self._runtime.create_workspace(feature_id, self._actor_id, parent)
        if not isinstance(workspace, QWidget):
            raise TypeError("Feature workspace must be a PySide6 QWidget.")
        workspace.setParent(parent)
        return workspace

    def shutdown_all(self) -> None:
        for unsubscribe in self._unsubscribe:
            unsubscribe()
        self._runtime.shutdown_all()

    def _on_lifecycle_event(self, event: object) -> None:
        payload = getattr(event, "payload", {})
        feature_id = payload.get("feature_id") if hasattr(payload, "get") else None
        if isinstance(feature_id, str):
            self.feature_unloaded.emit(feature_id)

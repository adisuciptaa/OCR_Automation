"""Public contracts and contexts for loading and activating feature modules."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from app.core.event_bus import EventBus
from app.core.service_registry import ServiceProvider
from app.feature_manager.models import FeatureDescriptor


@dataclass(frozen=True, slots=True)
class FeatureContext:
    """Application capabilities intentionally exposed to a loaded feature."""

    services: ServiceProvider
    event_bus: EventBus
    logger: logging.Logger
    feature_id: str


@dataclass(frozen=True, slots=True)
class UIContext:
    """Presentation context supplied when a feature workspace is requested."""

    parent: object
    actor_id: str
    feature_id: str


class FeatureModule(Protocol):
    def initialize(self, context: FeatureContext) -> None: ...
    def get_descriptor(self) -> FeatureDescriptor: ...
    def create_workspace(self, context: UIContext) -> object: ...
    def validate_configuration(self, config: object) -> object: ...
    def execute(self, request: object) -> object: ...
    def shutdown(self) -> None: ...

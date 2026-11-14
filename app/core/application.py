"""Application runtime orchestration for startup and shutdown."""

from __future__ import annotations

import logging

from app.core.config_manager import ConfigManager
from app.core.event_bus import ApplicationEvent, EventBus
from app.core.exceptions import LifecycleError
from app.core.lifecycle import LifecycleManager, LifecycleState
from app.core.service_registry import ServiceRegistry


class ApplicationRuntime:
    """Coordinates Core services without owning presentation or business logic."""

    def __init__(
        self,
        *,
        config: ConfigManager,
        event_bus: EventBus,
        service_registry: ServiceRegistry,
        lifecycle: LifecycleManager | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.config = config
        self.event_bus = event_bus
        self.service_registry = service_registry
        self.lifecycle = lifecycle or LifecycleManager()
        self.logger = logger or logging.getLogger(__name__)

    def initialize(self) -> None:
        if self.lifecycle.state is not LifecycleState.CREATED:
            raise LifecycleError(
                "APPLICATION_ALREADY_INITIALIZED",
                "Application runtime can only be initialized once.",
            )

        self.lifecycle.transition(LifecycleState.STARTING)
        try:
            self.config.load()
            self.lifecycle.transition(LifecycleState.RUNNING)
            self.event_bus.publish(
                ApplicationEvent(
                    event_name="application.started",
                    payload={"state": LifecycleState.RUNNING.value},
                )
            )
            self.logger.info("OCR Automation application runtime started.")
        except Exception:
            self.lifecycle.mark_failed()
            self.logger.exception("Application runtime initialization failed.")
            raise

    def shutdown(self) -> None:
        state = self.lifecycle.state
        if state is LifecycleState.STOPPED:
            return
        if state is LifecycleState.CREATED:
            self.lifecycle.transition(LifecycleState.STOPPED)
            return
        if state is LifecycleState.RUNNING or state is LifecycleState.FAILED:
            self.lifecycle.transition(LifecycleState.STOPPING)
        elif state is not LifecycleState.STOPPING:
            raise LifecycleError(
                "APPLICATION_SHUTDOWN_INVALID",
                f"Cannot shut down application from state '{state.value}'.",
            )

        self.event_bus.publish(
            ApplicationEvent(
                event_name="application.stopping",
                payload={"state": LifecycleState.STOPPING.value},
            )
        )
        self.lifecycle.transition(LifecycleState.STOPPED)
        self.logger.info("OCR Automation application runtime stopped.")

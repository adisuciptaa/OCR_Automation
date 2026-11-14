"""In-process typed application event bus."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import RLock
from types import MappingProxyType
from typing import Any
from uuid import uuid4

EventHandler = Callable[["ApplicationEvent"], None]


@dataclass(frozen=True, slots=True)
class ApplicationEvent:
    event_name: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid4()))
    event_version: str = "1.0"
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    correlation_id: str = field(default_factory=lambda: str(uuid4()))
    actor_id: str | None = None

    def __post_init__(self) -> None:
        if not self.event_name.strip():
            raise ValueError("event_name must not be blank")
        if self.timestamp.tzinfo is None:
            raise ValueError("event timestamp must be timezone-aware")
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


class EventBus:
    """Publishes events synchronously to subscribers of the matching event name."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._lock = RLock()
        self._logger = logger or logging.getLogger(__name__)

    def subscribe(self, event_name: str, handler: EventHandler) -> Callable[[], None]:
        if not event_name.strip():
            raise ValueError("event_name must not be blank")
        with self._lock:
            self._handlers[event_name].append(handler)

        def unsubscribe() -> None:
            with self._lock:
                handlers = self._handlers.get(event_name, [])
                if handler in handlers:
                    handlers.remove(handler)
                if not handlers:
                    self._handlers.pop(event_name, None)

        return unsubscribe

    def publish(self, event: ApplicationEvent) -> None:
        with self._lock:
            handlers = tuple(self._handlers.get(event.event_name, ()))

        for handler in handlers:
            try:
                handler(event)
            except Exception:
                self._logger.exception(
                    "Application event handler failed: event=%s event_id=%s",
                    event.event_name,
                    event.event_id,
                )

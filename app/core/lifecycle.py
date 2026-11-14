"""Thread-safe application lifecycle state management."""

from __future__ import annotations

from enum import StrEnum
from threading import RLock

from app.core.exceptions import LifecycleError


class LifecycleState(StrEnum):
    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


_ALLOWED_TRANSITIONS: dict[LifecycleState, frozenset[LifecycleState]] = {
    LifecycleState.CREATED: frozenset({LifecycleState.STARTING, LifecycleState.STOPPED}),
    LifecycleState.STARTING: frozenset({LifecycleState.RUNNING, LifecycleState.FAILED}),
    LifecycleState.RUNNING: frozenset({LifecycleState.STOPPING, LifecycleState.FAILED}),
    LifecycleState.STOPPING: frozenset({LifecycleState.STOPPED, LifecycleState.FAILED}),
    LifecycleState.STOPPED: frozenset(),
    LifecycleState.FAILED: frozenset({LifecycleState.STOPPING, LifecycleState.STOPPED}),
}


class LifecycleManager:
    """Owns valid state transitions for one application runtime."""

    def __init__(self) -> None:
        self._state = LifecycleState.CREATED
        self._lock = RLock()

    @property
    def state(self) -> LifecycleState:
        with self._lock:
            return self._state

    def transition(self, target: LifecycleState) -> LifecycleState:
        with self._lock:
            if target not in _ALLOWED_TRANSITIONS[self._state]:
                raise LifecycleError(
                    "APPLICATION_LIFECYCLE_INVALID",
                    f"Cannot transition application from {self._state} to {target}.",
                    details={"current_state": self._state.value, "target_state": target.value},
                )
            self._state = target
            return self._state

    def mark_failed(self) -> LifecycleState:
        with self._lock:
            if self._state in {LifecycleState.STOPPED, LifecycleState.FAILED}:
                return self._state
            self._state = LifecycleState.FAILED
            return self._state

from __future__ import annotations

import pytest

from app.core.exceptions import LifecycleError
from app.core.lifecycle import LifecycleManager, LifecycleState


def test_lifecycle_valid_start_and_stop_transitions() -> None:
    lifecycle = LifecycleManager()
    assert lifecycle.state is LifecycleState.CREATED
    lifecycle.transition(LifecycleState.STARTING)
    lifecycle.transition(LifecycleState.RUNNING)
    lifecycle.transition(LifecycleState.STOPPING)
    lifecycle.transition(LifecycleState.STOPPED)
    assert lifecycle.state is LifecycleState.STOPPED


def test_lifecycle_rejects_invalid_transition() -> None:
    lifecycle = LifecycleManager()
    with pytest.raises(LifecycleError) as error:
        lifecycle.transition(LifecycleState.RUNNING)
    assert error.value.code == "APPLICATION_LIFECYCLE_INVALID"


def test_lifecycle_can_mark_startup_failure() -> None:
    lifecycle = LifecycleManager()
    lifecycle.transition(LifecycleState.STARTING)
    lifecycle.mark_failed()
    assert lifecycle.state is LifecycleState.FAILED

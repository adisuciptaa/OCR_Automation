from __future__ import annotations

from app.core.application import ApplicationRuntime
from app.core.config_manager import ConfigManager
from app.core.event_bus import EventBus
from app.core.lifecycle import LifecycleState
from app.core.service_registry import ServiceRegistry


def test_application_runtime_initializes_and_shuts_down(tmp_path) -> None:
    received = []
    event_bus = EventBus()
    event_bus.subscribe("application.started", received.append)
    event_bus.subscribe("application.stopping", received.append)
    runtime = ApplicationRuntime(
        config=ConfigManager(tmp_path / "config.json"),
        event_bus=event_bus,
        service_registry=ServiceRegistry(),
    )

    runtime.initialize()
    assert runtime.lifecycle.state is LifecycleState.RUNNING
    runtime.shutdown()
    runtime.shutdown()

    assert runtime.lifecycle.state is LifecycleState.STOPPED
    assert [event.event_name for event in received] == [
        "application.started", "application.stopping"
    ]


def test_application_runtime_marks_failed_when_configuration_cannot_load(tmp_path) -> None:
    from app.core.exceptions import ConfigurationError

    config_path = tmp_path / "invalid.json"
    config_path.write_text("not-json", encoding="utf-8")
    runtime = ApplicationRuntime(
        config=ConfigManager(config_path),
        event_bus=EventBus(),
        service_registry=ServiceRegistry(),
    )

    try:
        runtime.initialize()
    except ConfigurationError as error:
        assert error.code == "CONFIGURATION_LOAD_FAILED"
    else:
        raise AssertionError("Expected configuration loading to fail.")

    assert runtime.lifecycle.state is LifecycleState.FAILED

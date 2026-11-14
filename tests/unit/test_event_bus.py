from __future__ import annotations

import logging

from app.core.event_bus import ApplicationEvent, EventBus


def test_event_bus_publishes_to_matching_subscribers() -> None:
    received = []
    bus = EventBus()
    bus.subscribe("job.started", received.append)
    bus.publish(ApplicationEvent(event_name="job.started", payload={"job_id": "job-1"}))
    assert len(received) == 1
    assert received[0].payload["job_id"] == "job-1"
    assert received[0].correlation_id


def test_event_bus_unsubscribe_stops_delivery() -> None:
    received = []
    bus = EventBus()
    unsubscribe = bus.subscribe("job.completed", received.append)
    unsubscribe()
    bus.publish(ApplicationEvent(event_name="job.completed"))
    assert received == []


def test_event_bus_logs_handler_failure_and_continues(caplog) -> None:
    received = []
    bus = EventBus(logging.getLogger("test.event_bus"))

    def broken_handler(event):
        raise RuntimeError("private diagnostic")

    bus.subscribe("app.started", broken_handler)
    bus.subscribe("app.started", received.append)
    with caplog.at_level(logging.ERROR):
        bus.publish(ApplicationEvent(event_name="app.started"))
    assert len(received) == 1
    assert "Application event handler failed" in caplog.text
    assert "RuntimeError" in caplog.text

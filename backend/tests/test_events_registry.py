"""The event registry round-trips events across the transport boundary."""

from __future__ import annotations

from hades.contexts.notification.domain.events import NotificationRequested
from hades.contexts.notification.domain.ports import Severity
from hades.shared_kernel.domain.identifiers import new_id
from hades.shared_kernel.events import EventRegistry


def test_registry_rebuilds_typed_event_from_envelope() -> None:
    registry = EventRegistry()
    registry.register(NotificationRequested)

    original = NotificationRequested(
        aggregate_id=new_id(),
        title="t",
        body="b",
        severity=Severity.CRITICAL,
        tags={"topic": "risk"},
    )
    envelope = original.to_envelope()

    rebuilt = registry.rebuild(envelope)
    assert isinstance(rebuilt, NotificationRequested)
    assert rebuilt.title == "t"
    assert rebuilt.severity is Severity.CRITICAL
    assert rebuilt.tags == {"topic": "risk"}


def test_registry_ignores_unknown_event() -> None:
    registry = EventRegistry()
    assert registry.rebuild({"event_type": "Nope", "payload": {}}) is None

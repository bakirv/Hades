"""Notifications flow through events only, and the service gates by severity."""

from __future__ import annotations

from hades.contexts.notification.application.publisher import NotificationPublisher
from hades.contexts.notification.application.service import NotificationService
from hades.contexts.notification.domain.ports import Notification, Notifier, Severity
from hades.shared_kernel.events import InMemoryEventBus


class _FakeNotifier(Notifier):
    def __init__(self) -> None:
        self.sent: list[Notification] = []

    @property
    def channel(self) -> str:
        return "discord"

    async def send(self, notification: Notification) -> None:
        self.sent.append(notification)


async def test_publisher_and_service_deliver_via_events() -> None:
    bus = InMemoryEventBus()
    notifier = _FakeNotifier()
    service = NotificationService([notifier], min_severity=Severity.INFO)
    service.register(bus)

    publisher = NotificationPublisher(bus)
    await publisher.notify(title="hello", body="world", severity=Severity.WARNING)

    assert len(notifier.sent) == 1
    assert notifier.sent[0].title == "hello"
    assert notifier.sent[0].severity is Severity.WARNING


async def test_severity_below_threshold_is_dropped() -> None:
    bus = InMemoryEventBus()
    notifier = _FakeNotifier()
    service = NotificationService([notifier], min_severity=Severity.WARNING)
    service.register(bus)

    await NotificationPublisher(bus).notify(title="debug", body="x", severity=Severity.INFO)
    assert notifier.sent == []

"""Notification publisher — the sanctioned way to *request* a notification.

Modules that want to alert the operator call :meth:`NotificationPublisher.notify`,
which publishes a :class:`NotificationRequested` event. They never construct a
notifier or touch Discord. The Notification Service decides delivery.
"""

from __future__ import annotations

from hades.contexts.notification.domain.events import NotificationRequested
from hades.contexts.notification.domain.ports import Severity
from hades.shared_kernel.domain.identifiers import new_id
from hades.shared_kernel.events import EventBus


class NotificationPublisher:
    """A thin helper other contexts use to request a notification via the bus."""

    def __init__(self, event_bus: EventBus) -> None:
        self._bus = event_bus

    async def notify(
        self,
        *,
        title: str,
        body: str,
        severity: Severity = Severity.INFO,
        channel: str = "discord",
        tags: dict[str, str] | None = None,
        dedup_key: str | None = None,
    ) -> None:
        await self._bus.publish(
            NotificationRequested(
                aggregate_id=new_id(),
                title=title,
                body=body,
                severity=severity,
                channel=channel,
                tags=tags or {},
                dedup_key=dedup_key,
            )
        )

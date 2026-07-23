"""Domain events for the Notification context.

Other modules never call Discord (or any transport) directly. They **publish a
``NotificationRequested`` event**; the Notification Service is the only consumer
that decides whether and how to deliver it. This keeps every module decoupled
from the delivery channel and gives a single, auditable choke point for alerts.
"""

from __future__ import annotations

from hades.contexts.notification.domain.ports import Severity
from hades.shared_kernel.domain.events import DomainEvent


class NotificationRequested(DomainEvent):
    """A module asked for a notification to be delivered."""

    aggregate_type: str = "notification"
    title: str
    body: str
    severity: Severity
    channel: str = "discord"
    tags: dict[str, str] = {}
    dedup_key: str | None = None

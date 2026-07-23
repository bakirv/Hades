"""Domain-event type registry.

When events cross a process boundary (the Redis transport) they travel as JSON
envelopes and must be reconstituted into their concrete :class:`DomainEvent`
subclass on the other side. The registry maps ``event_type`` (the class name) to
the class so the transport can rebuild the exact typed event a handler expects.

Contexts register their events at wiring time (``bootstrap``); the in-memory bus
does not need this (it passes the live object), so this only matters for Redis.
"""

from __future__ import annotations

from typing import Any

from hades.shared_kernel.domain.events import DomainEvent
from hades.shared_kernel.logging import get_logger

_logger = get_logger("events.registry")


class EventRegistry:
    """Name → ``DomainEvent`` subclass lookup for deserialisation."""

    def __init__(self) -> None:
        self._types: dict[str, type[DomainEvent]] = {}

    def register(self, *event_types: type[DomainEvent]) -> None:
        for event_type in event_types:
            self._types[event_type.__name__] = event_type
            _logger.debug("event_type_registered", event_type=event_type.__name__)

    def get(self, event_type: str) -> type[DomainEvent] | None:
        return self._types.get(event_type)

    def rebuild(self, envelope: dict[str, Any]) -> DomainEvent | None:
        """Reconstruct a typed event from a transport envelope, or None if the
        type is unknown to this process (safely ignored)."""
        event_type = envelope.get("event_type", "")
        cls = self._types.get(event_type)
        if cls is None:
            return None
        payload = envelope.get("payload", {})
        fields = {
            "event_id": envelope["event_id"],
            "aggregate_id": envelope["aggregate_id"],
            "aggregate_type": envelope["aggregate_type"],
            "occurred_at": envelope["occurred_at"],
            "version": envelope.get("version", -1),
            "correlation_id": envelope.get("correlation_id"),
            "causation_id": envelope.get("causation_id"),
            **payload,
        }
        return cls.model_validate(fields)

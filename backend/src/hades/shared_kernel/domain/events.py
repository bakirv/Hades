"""Domain event base class.

A *domain event* is an immutable fact: something that already happened, named in
the past tense (``TokenDiscovered``, ``PositionOpened``). Events are the
backbone of Hades — every meaningful action produces one, they are persisted
append-only in the event store (event sourcing) and published on the event bus
so other contexts can react (event-driven architecture).

Concrete events live in each context's ``domain/events.py`` and subclass this.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from hades.shared_kernel.domain.identifiers import EntityId, new_id


class DomainEvent(BaseModel):
    """Immutable record of something that happened in the domain.

    Metadata fields are common to every event; subclasses add their payload.
    ``event_type`` defaults to the class name and is what the bus routes on.
    ``aggregate_id`` ties the event to the stream it belongs to.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: EntityId = Field(default_factory=new_id)
    aggregate_id: EntityId
    aggregate_type: str
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    # Monotonic version of the aggregate at which this event applies. Set by the
    # event store on append; -1 means "not yet persisted".
    version: int = -1
    # Free-form correlation/causation ids for tracing a decision across contexts.
    correlation_id: EntityId | None = None
    causation_id: EntityId | None = None

    @property
    def event_type(self) -> str:
        return type(self).__name__

    def to_envelope(self) -> dict[str, Any]:
        """Serialise to a transport-agnostic envelope (bus + store use this)."""
        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "aggregate_id": str(self.aggregate_id),
            "aggregate_type": self.aggregate_type,
            "occurred_at": self.occurred_at.isoformat(),
            "version": self.version,
            "correlation_id": str(self.correlation_id) if self.correlation_id else None,
            "causation_id": str(self.causation_id) if self.causation_id else None,
            "payload": self.model_dump(
                mode="json",
                exclude={
                    "event_id",
                    "aggregate_id",
                    "aggregate_type",
                    "occurred_at",
                    "version",
                    "correlation_id",
                    "causation_id",
                },
            ),
        }

"""Entity, ValueObject and AggregateRoot base classes.

- **ValueObject**: immutable, compared by value, has no identity (e.g. a price,
  a percentage, a token mint address).
- **Entity**: has a stable identity (``id``); compared by identity, not value.
- **AggregateRoot**: an entity that is the consistency boundary and the only
  thing repositories persist. It records uncommitted :class:`DomainEvent`s as it
  changes; the application layer collects and publishes them after a successful
  commit.
"""

from __future__ import annotations

from abc import ABC
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from hades.shared_kernel.domain.events import DomainEvent
from hades.shared_kernel.domain.identifiers import EntityId, new_id


class ValueObject(BaseModel):
    """Immutable, equality-by-value object with no identity."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Entity(BaseModel):
    """Object with identity. Equality and hashing are by ``id`` only."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    id: EntityId = Field(default_factory=new_id)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Entity) and self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)


class AggregateRoot(Entity, ABC):
    """Consistency boundary and unit of persistence.

    Subclasses mutate state through methods that call :meth:`_record`, appending
    a domain event and bumping the version. The repository/unit-of-work reads
    :meth:`pull_events` after committing to hand events to the bus.
    """

    version: int = 0
    _pending_events: list[DomainEvent] = []

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        # Per-instance mutable buffer (avoid the shared class-level list).
        object.__setattr__(self, "_pending_events", [])

    def _record(self, event: DomainEvent) -> None:
        """Append a domain event and advance the aggregate version."""
        self.version += 1
        self._pending_events.append(event)

    def pull_events(self) -> list[DomainEvent]:
        """Return and clear the uncommitted events (called after commit)."""
        events = list(self._pending_events)
        self._pending_events.clear()
        return events

    @property
    def has_pending_events(self) -> bool:
        return bool(self._pending_events)

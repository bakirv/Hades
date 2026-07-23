"""Event store — append-only source of truth (event sourcing).

Every domain event is persisted forever, in order, per aggregate stream. The
current state of any aggregate is a fold over its event stream; nothing is ever
updated in place, so the full history of *why* a decision was made is
reconstructable — a hard requirement for a quant platform ("nunca perder el
historial").

The port is :class:`EventStore`. The production adapter writes to PostgreSQL
(see ``infrastructure``); :class:`InMemoryEventStore` backs tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from hades.shared_kernel.domain.events import DomainEvent
from hades.shared_kernel.domain.identifiers import EntityId
from hades.shared_kernel.errors import ConcurrencyError


@dataclass(frozen=True, slots=True)
class StoredEvent:
    """An event as persisted, with its assigned global sequence + version."""

    sequence: int
    version: int
    envelope: dict[str, Any]


@runtime_checkable
class EventStore(Protocol):
    """Append-only, per-aggregate event log with optimistic concurrency."""

    async def append(
        self,
        aggregate_id: EntityId,
        aggregate_type: str,
        events: list[DomainEvent],
        *,
        expected_version: int,
    ) -> None:
        """Append events to a stream.

        ``expected_version`` is the aggregate version the caller loaded. If the
        stored stream has advanced past it, raise :class:`ConcurrencyError` so
        the command can be retried against fresh state.
        """
        ...

    async def load_stream(self, aggregate_id: EntityId) -> list[StoredEvent]:
        """Return all events for one aggregate, ordered by version."""
        ...

    async def read_all(self, *, from_sequence: int = 0, limit: int = 500) -> list[StoredEvent]:
        """Read across all streams by global sequence (for projections)."""
        ...


class InMemoryEventStore:
    """Reference in-memory implementation (tests / single process)."""

    def __init__(self) -> None:
        self._streams: dict[EntityId, list[StoredEvent]] = {}
        self._global: list[StoredEvent] = []
        self._sequence = 0

    async def append(
        self,
        aggregate_id: EntityId,
        aggregate_type: str,
        events: list[DomainEvent],
        *,
        expected_version: int,
    ) -> None:
        stream = self._streams.setdefault(aggregate_id, [])
        current_version = stream[-1].version if stream else 0
        if current_version != expected_version:
            raise ConcurrencyError(
                "stale aggregate version on append",
                context={
                    "aggregate_id": str(aggregate_id),
                    "expected": expected_version,
                    "actual": current_version,
                },
            )
        version = current_version
        for event in events:
            version += 1
            self._sequence += 1
            stored = StoredEvent(
                sequence=self._sequence,
                version=version,
                envelope={**event.to_envelope(), "version": version},
            )
            stream.append(stored)
            self._global.append(stored)

    async def load_stream(self, aggregate_id: EntityId) -> list[StoredEvent]:
        return list(self._streams.get(aggregate_id, []))

    async def read_all(self, *, from_sequence: int = 0, limit: int = 500) -> list[StoredEvent]:
        return [e for e in self._global if e.sequence > from_sequence][:limit]

"""Event-sourcing tables — the append-only source of truth.

``domain_events`` is the immutable log every aggregate is folded from. A global
``sequence`` gives total order for projections; ``(aggregate_id, version)`` is
unique to enforce optimistic concurrency at the database level. Nothing is ever
updated in place — this is the platform's "never lose the history" guarantee.

``event_snapshots`` is an optional optimisation (fold acceleration); it is never
authoritative — the events are.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hades.shared_kernel.persistence.database import Base
from hades.shared_kernel.persistence.models._mixins import TimestampMixin, UUIDPrimaryKeyMixin


class DomainEventRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One persisted domain event. ``id`` equals the event's ``event_id``."""

    __tablename__ = "domain_events"
    __table_args__ = (
        UniqueConstraint("aggregate_id", "version", name="uq_domain_events_aggregate_version"),
    )

    sequence: Mapped[int] = mapped_column(
        BigInteger, autoincrement=True, unique=True, index=True, nullable=False
    )
    aggregate_id: Mapped[uuid.UUID] = mapped_column(index=True, nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    correlation_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    causation_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class EventSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Materialised aggregate state at a given version (fold acceleration)."""

    __tablename__ = "event_snapshots"
    __table_args__ = (
        UniqueConstraint("aggregate_id", "version", name="uq_event_snapshots_aggregate_version"),
    )

    aggregate_id: Mapped[uuid.UUID] = mapped_column(index=True, nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

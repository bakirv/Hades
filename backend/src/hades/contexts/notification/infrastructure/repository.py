"""Persistence of notifications for the audit trail.

Implements the :class:`NotificationRecorder` protocol used by the Notification
Service. Every requested notification is written as ``pending`` and then marked
``sent`` or ``failed``, so the platform keeps a durable record of what it tried
to tell the operator.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import update

from hades.contexts.notification.domain.events import NotificationRequested
from hades.shared_kernel.persistence.database import Database
from hades.shared_kernel.persistence.models import Notification as NotificationRow


class NotificationRepository:
    """SQLAlchemy-backed recorder for outbound notifications."""

    def __init__(self, database: Database) -> None:
        self._db = database

    async def record_pending(self, event: NotificationRequested) -> str:
        row = NotificationRow(
            title=event.title,
            body=event.body,
            severity=event.severity.value,
            channel=event.channel,
            status="pending",
            dedup_key=event.dedup_key,
            tags=dict(event.tags),
        )
        async with self._db.session() as session:
            session.add(row)
            await session.flush()
            record_id = str(row.id)
        return record_id

    async def mark_sent(self, record_id: str) -> None:
        async with self._db.session() as session:
            await session.execute(
                update(NotificationRow)
                .where(NotificationRow.id == record_id)
                .values(status="sent", sent_at=datetime.now(UTC))
            )

    async def mark_failed(self, record_id: str, error: str) -> None:
        async with self._db.session() as session:
            await session.execute(
                update(NotificationRow)
                .where(NotificationRow.id == record_id)
                .values(status="failed", error=error)
            )

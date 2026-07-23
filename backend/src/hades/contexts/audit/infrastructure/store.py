"""Audit stores — the append-only ``audit_log`` adapter and an in-memory twin.

The Postgres adapter reuses the pre-existing ``audit_log`` table (declared in the
baseline schema and mixin-timestamped), so no migration is needed. ``entity_id``
is stored as a UUID only when the domain value parses as one (aggregate-scoped
actions); platform-wide actions leave it null and carry their subject in
``action``/``entity_type``.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from hades.contexts.audit.domain.models import AuditEntry, AuditQuery
from hades.shared_kernel.persistence.database import Database
from hades.shared_kernel.persistence.models import AuditLog


def _as_uuid(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        return None


class PostgresAuditStore:
    """Append/query the append-only ``audit_log`` table."""

    def __init__(self, database: Database) -> None:
        self._db = database

    async def append(self, entry: AuditEntry) -> None:
        async with self._db.session() as session:
            session.add(
                AuditLog(
                    actor=entry.actor,
                    action=entry.action,
                    entity_type=entry.entity_type,
                    entity_id=_as_uuid(entry.entity_id),
                    before=entry.before,
                    after=entry.after,
                    source_ip=entry.source_ip,
                    occurred_at=entry.occurred_at,
                )
            )

    async def query(self, spec: AuditQuery) -> list[AuditEntry]:
        stmt = select(AuditLog)
        if spec.actor:
            stmt = stmt.where(AuditLog.actor == spec.actor)
        if spec.action:
            stmt = stmt.where(AuditLog.action == spec.action)
        if spec.entity_type:
            stmt = stmt.where(AuditLog.entity_type == spec.entity_type)
        if spec.since:
            stmt = stmt.where(AuditLog.occurred_at >= spec.since)
        if spec.until:
            stmt = stmt.where(AuditLog.occurred_at <= spec.until)
        stmt = stmt.order_by(AuditLog.occurred_at.desc()).limit(spec.limit).offset(spec.offset)

        async with self._db.session() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return [_to_entry(row) for row in rows]


class InMemoryAuditStore:
    """In-memory audit store for tests and single-process dev."""

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    @property
    def entries(self) -> list[AuditEntry]:
        return list(self._entries)

    async def append(self, entry: AuditEntry) -> None:
        self._entries.append(entry)

    async def query(self, spec: AuditQuery) -> list[AuditEntry]:
        rows = [e for e in self._entries if self._matches(e, spec)]
        rows.sort(key=lambda e: e.occurred_at, reverse=True)
        return rows[spec.offset : spec.offset + spec.limit]

    @staticmethod
    def _matches(entry: AuditEntry, spec: AuditQuery) -> bool:
        if spec.actor and entry.actor != spec.actor:
            return False
        if spec.action and entry.action != spec.action:
            return False
        if spec.entity_type and entry.entity_type != spec.entity_type:
            return False
        if spec.since and entry.occurred_at < spec.since:
            return False
        if spec.until and entry.occurred_at > spec.until:  # noqa: SIM103
            return False
        return True


def _to_entry(row: AuditLog) -> AuditEntry:
    return AuditEntry(
        actor=row.actor,
        action=row.action,
        entity_type=row.entity_type,
        entity_id=str(row.entity_id) if row.entity_id is not None else None,
        before=row.before,
        after=row.after,
        source_ip=row.source_ip,
        occurred_at=row.occurred_at,
    )

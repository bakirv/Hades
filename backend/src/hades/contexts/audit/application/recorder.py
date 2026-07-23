"""AuditRecorder — the :class:`AuditTrail` implementation.

A thin, defensive wrapper over an :class:`AuditStore`. Its single guarantee: a
failure to persist an audit entry is logged but **never propagates** — auditing
must never be the reason a legitimate action fails. It also normalises the
common ``record(...)`` keyword call into an :class:`AuditEntry`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from hades.contexts.audit.domain.models import AuditEntry
from hades.contexts.audit.domain.ports import AuditStore
from hades.shared_kernel.logging import get_logger

_logger = get_logger("audit.recorder")


class AuditRecorder:
    """Records audit entries; swallows persistence errors by design."""

    def __init__(self, store: AuditStore) -> None:
        self._store = store

    async def record(self, entry: AuditEntry) -> None:
        try:
            await self._store.append(entry)
        except Exception as exc:  # auditing must never break the audited action
            _logger.error(
                "audit_persist_failed", action=entry.action, actor=entry.actor, error=str(exc)
            )

    async def log(
        self,
        *,
        actor: str,
        action: str,
        entity_type: str | None = None,
        entity_id: str | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        source_ip: str | None = None,
    ) -> None:
        """Convenience: build an :class:`AuditEntry` and record it."""
        await self.record(
            AuditEntry(
                actor=actor,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                before=before,
                after=after,
                source_ip=source_ip,
                occurred_at=datetime.now(UTC),
            )
        )

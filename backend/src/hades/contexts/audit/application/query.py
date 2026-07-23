"""AuditQueryService — read side of the trail (for the API / dashboard)."""

from __future__ import annotations

from hades.contexts.audit.domain.models import AuditEntry, AuditQuery
from hades.contexts.audit.domain.ports import AuditStore


class AuditQueryService:
    """Reads the append-only audit trail with optional filtering."""

    def __init__(self, store: AuditStore) -> None:
        self._store = store

    async def search(self, spec: AuditQuery) -> list[AuditEntry]:
        return await self._store.query(spec)

"""Audit endpoint — read the append-only trail of consequential actions.

Read-only: the trail is written by the platform (recorder + subscriber), never by
an API caller. Supports filtering by actor / action / entity type / time window.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from hades.api.dependencies import get_container
from hades.bootstrap import Container
from hades.contexts.audit.application.query import AuditQueryService
from hades.contexts.audit.domain.models import AuditQuery
from hades.contexts.audit.infrastructure.store import InMemoryAuditStore, PostgresAuditStore

router = APIRouter(prefix="/api/v1", tags=["audit"])


def _query_service(container: Container) -> AuditQueryService:
    store = (
        PostgresAuditStore(container.database)
        if container.database is not None
        else InMemoryAuditStore()
    )
    return AuditQueryService(store)


@router.get("/audit", summary="Query the append-only audit trail")
async def audit(
    container: Container = Depends(get_container),
    actor: str | None = Query(default=None),
    action: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    spec = AuditQuery(
        actor=actor,
        action=action,
        entity_type=entity_type,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )
    entries = await _query_service(container).search(spec)
    return {
        "count": len(entries),
        "limit": limit,
        "offset": offset,
        "entries": [e.model_dump(mode="json") for e in entries],
    }

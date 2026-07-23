"""Scanner endpoint — live data-acquisition status for the dashboard.

Reports discovery-only information: tokens analysed / new, active DEX sources,
active RPC + latency, features/second, processing-queue depth and active workers.
It carries **no** risk or scoring information (that is a later phase).

Live runtime figures are read from the transient status the Worker publishes to
Redis; cumulative counts come from PostgreSQL. Cheap enough to poll frequently.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from hades.api.dependencies import get_container
from hades.bootstrap import Container
from hades.ops.scanner_runtime import SCANNER_STATUS_KEY, SCANNER_STATUS_NAMESPACE
from hades.shared_kernel.cache import CacheService
from hades.shared_kernel.persistence.models import DataAnomaly, Token

router = APIRouter(prefix="/api/v1/scanner", tags=["scanner"])


@router.get("/status", summary="Live scanner status (discovery only)")
async def scanner_status(
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    live = await _live_status(container)
    counts = await _counts(container)
    enabled = container.settings.scanner.enabled
    return {
        "enabled": enabled,
        "running": live is not None,
        "configured_sources": container.settings.scanner.source_list,
        **counts,
        "live": live or {},
    }


async def _live_status(container: Container) -> dict[str, Any] | None:
    cache = CacheService(container.redis, namespace=SCANNER_STATUS_NAMESPACE)
    try:
        result = await cache.get(SCANNER_STATUS_KEY)
    except Exception:  # dashboard must render even if Redis is down
        return None
    return result if isinstance(result, dict) else None


async def _counts(container: Container) -> dict[str, Any]:
    empty = {"tokens_total": 0, "tokens_active_1h": 0, "anomalies_total": 0}
    if container.database is None:
        return empty
    cutoff = datetime.now(UTC) - timedelta(hours=1)
    try:
        async with container.database.session() as session:
            tokens_total = await session.scalar(select(func.count()).select_from(Token))
            tokens_active = await session.scalar(
                select(func.count()).select_from(Token).where(Token.first_seen_at >= cutoff)
            )
            anomalies = await session.scalar(select(func.count()).select_from(DataAnomaly))
    except Exception:  # never fail the endpoint on a DB hiccup
        return empty
    return {
        "tokens_total": int(tokens_total or 0),
        "tokens_active_1h": int(tokens_active or 0),
        "anomalies_total": int(anomalies or 0),
    }

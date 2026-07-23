"""Status endpoint — live runtime posture for the dashboard header.

Reports version, environment, effective trading mode + live flag, event-bus
transport and process uptime. Intentionally cheap (no dependency probing — that
is the Watchdog's job and ``/health``'s) so the dashboard can poll/subscribe it
frequently without load.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Request

from hades import __version__
from hades.api.dependencies import get_container, get_trading_mode_service
from hades.bootstrap import Container
from hades.contexts.execution.application.trading_mode import TradingModeService

router = APIRouter(prefix="/api/v1", tags=["status"])


@router.get("/status", summary="Live runtime status")
async def status(
    request: Request,
    container: Container = Depends(get_container),
    mode_service: TradingModeService = Depends(get_trading_mode_service),
) -> dict[str, object]:
    s = container.settings
    started_at = getattr(request.app.state, "started_at", time.time())
    mode = await mode_service.current()
    return {
        "name": "hades",
        "version": __version__,
        "role": container.role,
        "environment": s.env,
        "instance_id": s.instance_id,
        "trading_mode": mode.mode,
        "is_live": mode.is_live,
        "live_gate_enabled": mode.live_gate_enabled,
        "event_bus_transport": s.event_bus.transport,
        "uptime_seconds": round(time.time() - started_at, 1),
    }

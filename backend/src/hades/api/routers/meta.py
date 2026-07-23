"""Meta/introspection endpoints — version, config posture, registered contexts."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from hades import __version__
from hades.api.dependencies import get_container
from hades.bootstrap import Container

router = APIRouter(prefix="/api/v1", tags=["meta"])

# The bounded contexts that make up the platform (kept in sync with hades.md).
_CONTEXTS = [
    "scanner",
    "features",
    "security",
    "wallet",
    "market",
    "scoring",
    "risk",
    "portfolio",
    "execution",
    "learning",
    "research",
    "notification",
    "monitoring",
]


@router.get("/meta", summary="Platform version + runtime posture")
async def meta(container: Container = Depends(get_container)) -> dict[str, object]:
    s = container.settings
    return {
        "name": "hades",
        "version": __version__,
        "environment": s.env,
        "trading_mode": s.trading_mode,
        "is_live": s.is_live,
        "event_bus_transport": s.event_bus.transport,
        "contexts": _CONTEXTS,
    }

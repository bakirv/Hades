"""Info endpoint — static description of the platform: contexts and services."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from hades import __version__
from hades.api.dependencies import get_container
from hades.bootstrap import Container

router = APIRouter(prefix="/api/v1", tags=["meta"])

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

_SERVICES = [
    "postgres",
    "redis",
    "api",
    "dashboard",
    "engine",
    "watchdog",
    "scheduler",
    "worker",
    "notification",
]


@router.get("/info", summary="Platform description: contexts, services, capabilities")
async def info(container: Container = Depends(get_container)) -> dict[str, object]:
    s = container.settings
    return {
        "name": "hades",
        "version": __version__,
        "description": "Professional quantitative platform for Solana meme coins.",
        "phase": "Phase 2 — Platform infrastructure",
        "contexts": _CONTEXTS,
        "services": _SERVICES,
        "capabilities": {
            "trading": "paper-only (live hard-gated)",
            "event_bus_transport": s.event_bus.transport,
            "clickhouse_enabled": s.clickhouse.enabled,
            "notifications": "discord" if s.notification.discord_enabled else "disabled",
            "auth_enabled": s.api.auth_enabled,
        },
    }

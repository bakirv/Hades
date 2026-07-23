"""Ports defined by the Monitoring context."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from hades.contexts.monitoring.domain.models import ComponentHealth


@runtime_checkable
class HealthProbe(Protocol):
    """Checks the health of one dependency or component on demand.

    The Health Monitor runs every registered probe to build a ``SystemHealth``.
    Each dependency (Postgres, Redis, RPC, event bus) ships its own probe.
    """

    @property
    def name(self) -> str: ...

    async def check(self) -> ComponentHealth: ...


@runtime_checkable
class HeartbeatSink(Protocol):
    """Records heartbeats and reports which components are overdue (Watchdog)."""

    async def beat(self, component: str) -> None: ...

    async def overdue(self) -> list[str]: ...

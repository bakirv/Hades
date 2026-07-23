"""Concrete recovery actions + Emergency-Mode flag persistence.

Each action is a small, bounded, side-effecting attempt to heal one class of
failure, catching its own errors and reporting success as a bool (never raising
into the orchestrator loop). The composition root wires only the actions that are
meaningful in that process.

``PostgresEmergencyFlagStore`` persists the Emergency-Mode flag in the existing
``system_configuration`` table (key ``emergency_mode``), so the halt survives a
restart and the Production Checklist can read it to keep LIVE blocked.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from sqlalchemy import select, text

from hades.shared_kernel.cache import RedisProvider
from hades.shared_kernel.config import get_settings
from hades.shared_kernel.logging import get_logger
from hades.shared_kernel.persistence.database import Database
from hades.shared_kernel.persistence.models import SystemConfiguration

_logger = get_logger("monitoring.recovery.actions")

_EMERGENCY_KEY = "emergency_mode"


@runtime_checkable
class _RpcLike(Protocol):
    async def health_check(self) -> bool: ...


class RedisReconnectAction:
    """Drop and re-establish the Redis connection, verifying with a ping."""

    def __init__(self, redis: RedisProvider) -> None:
        self._redis = redis

    @property
    def name(self) -> str:
        return "redis_reconnect"

    def handles(self, component: str) -> bool:
        return "redis" in component.lower()

    async def attempt(self) -> bool:
        try:
            await self._redis.close()
            return await self._redis.ping()
        except Exception as exc:
            _logger.warning("redis_reconnect_failed", error=str(exc))
            return False


class PostgresReconnectAction:
    """Dispose the engine's pool (forcing fresh connections) and test one."""

    def __init__(self, database: Database) -> None:
        self._db = database

    @property
    def name(self) -> str:
        return "postgres_reconnect"

    def handles(self, component: str) -> bool:
        lowered = component.lower()
        return "postgres" in lowered or "database" in lowered

    async def attempt(self) -> bool:
        try:
            await self._db.engine.dispose()
            async with self._db.session() as session:
                await session.execute(text("SELECT 1"))
            return True
        except Exception as exc:
            _logger.warning("postgres_reconnect_failed", error=str(exc))
            return False


class RpcFailoverAction:
    """Re-probe RPC providers and re-elect a healthy endpoint."""

    def __init__(self, rpc: _RpcLike) -> None:
        self._rpc = rpc

    @property
    def name(self) -> str:
        return "rpc_failover"

    def handles(self, component: str) -> bool:
        return "rpc" in component.lower()

    async def attempt(self) -> bool:
        try:
            return await self._rpc.health_check()
        except Exception as exc:
            _logger.warning("rpc_failover_failed", error=str(exc))
            return False


class ConfigReloadAction:
    """Clear the cached settings so the next read re-loads configuration."""

    @property
    def name(self) -> str:
        return "config_reload"

    def handles(self, component: str) -> bool:
        lowered = component.lower()
        return "config" in lowered

    async def attempt(self) -> bool:
        try:
            get_settings.cache_clear()
            return True
        except Exception as exc:
            _logger.warning("config_reload_failed", error=str(exc))
            return False


class PostgresEmergencyFlagStore:
    """Persists the Emergency-Mode flag in ``system_configuration``."""

    def __init__(self, database: Database) -> None:
        self._db = database

    async def is_active(self) -> bool:
        async with self._db.session() as session:
            row = (
                await session.execute(
                    select(SystemConfiguration).where(SystemConfiguration.key == _EMERGENCY_KEY)
                )
            ).scalar_one_or_none()
        if row is None or not isinstance(row.value, dict):
            return False
        return bool(row.value.get("active", False))

    async def set_active(self, active: bool, *, reason: str, actor: str) -> None:
        value = {"active": active, "reason": reason, "at": datetime.now(UTC).isoformat()}
        async with self._db.session() as session:
            row = (
                await session.execute(
                    select(SystemConfiguration).where(SystemConfiguration.key == _EMERGENCY_KEY)
                )
            ).scalar_one_or_none()
            if row is None:
                session.add(
                    SystemConfiguration(
                        key=_EMERGENCY_KEY,
                        value=value,
                        value_type="json",
                        description="Emergency Mode flag (auto-recovery escalation).",
                        updated_by=actor,
                    )
                )
            else:
                row.value = value
                row.updated_by = actor


class InMemoryEmergencyFlagStore:
    """In-memory Emergency-Mode flag for tests / no-database dev."""

    def __init__(self) -> None:
        self._active = False
        self.reason = ""

    async def is_active(self) -> bool:
        return self._active

    async def set_active(self, active: bool, *, reason: str, actor: str) -> None:
        self._active = active
        self.reason = reason

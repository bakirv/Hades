"""Persistence for the trading-mode switch.

The effective trading mode is stored in ``system_configuration`` (DB authority)
so it survives restarts and stays consistent across API/dashboard/services. Every
change is also written to the append-only ``audit_log`` and recorded as a
``risk_event`` — switching to live is the single most consequential action on the
platform and must be fully traceable.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from hades.shared_kernel.persistence.database import Database
from hades.shared_kernel.persistence.models import AuditLog, RiskEvent, SystemConfiguration

_MODE_KEY = "trading_mode"


class TradingModeRepository:
    """Reads/writes the persisted trading mode with full audit trail."""

    def __init__(self, database: Database) -> None:
        self._db = database

    async def get_mode(self) -> str | None:
        async with self._db.session() as session:
            row = (
                await session.execute(
                    select(SystemConfiguration).where(SystemConfiguration.key == _MODE_KEY)
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            return str(row.value.get("mode")) if isinstance(row.value, dict) else None

    async def set_mode(
        self, mode: str, *, previous_mode: str, actor: str, source_ip: str | None = None
    ) -> None:
        now = datetime.now(UTC)
        async with self._db.session() as session:
            row = (
                await session.execute(
                    select(SystemConfiguration).where(SystemConfiguration.key == _MODE_KEY)
                )
            ).scalar_one_or_none()
            if row is None:
                session.add(
                    SystemConfiguration(
                        key=_MODE_KEY,
                        value={"mode": mode},
                        value_type="json",
                        description="Effective platform trading mode (paper|live).",
                        updated_by=actor,
                    )
                )
            else:
                row.value = {"mode": mode}
                row.updated_by = actor

            session.add(
                AuditLog(
                    actor=actor,
                    action="trading_mode_change",
                    entity_type="platform",
                    before={"mode": previous_mode},
                    after={"mode": mode},
                    source_ip=source_ip,
                    occurred_at=now,
                )
            )
            session.add(
                RiskEvent(
                    kind="trading_mode_change",
                    severity="critical" if mode == "live" else "warning",
                    mode=mode,
                    message=f"trading mode changed {previous_mode} -> {mode} by {actor}",
                    details={"previous_mode": previous_mode, "new_mode": mode, "actor": actor},
                    occurred_at=now,
                )
            )

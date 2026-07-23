"""Persistence for monitoring: health-check results and risk events."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from hades.contexts.monitoring.domain.models import ComponentHealth, SystemHealth
from hades.shared_kernel.persistence.database import Database
from hades.shared_kernel.persistence.models import HealthCheck as HealthCheckRow
from hades.shared_kernel.persistence.models import RiskEvent as RiskEventRow


class MonitoringRepository:
    """Writes health-check rows and risk events to PostgreSQL."""

    def __init__(self, database: Database, *, instance_id: str = "hades") -> None:
        self._db = database
        self._instance_id = instance_id

    async def record_health(
        self, health: SystemHealth, *, latencies: dict[str, float] | None = None
    ) -> None:
        latencies = latencies or {}
        checked_at = datetime.now(UTC)
        async with self._db.session() as session:
            for component in health.components:
                session.add(
                    HealthCheckRow(
                        component=component.name,
                        status=component.status.value,
                        detail=component.detail,
                        latency_ms=latencies.get(component.name),
                        instance_id=self._instance_id,
                        checked_at=checked_at,
                    )
                )

    async def record_component(self, component: ComponentHealth) -> None:
        async with self._db.session() as session:
            session.add(
                HealthCheckRow(
                    component=component.name,
                    status=component.status.value,
                    detail=component.detail,
                    instance_id=self._instance_id,
                    checked_at=datetime.now(UTC),
                )
            )

    async def record_risk_event(
        self, *, kind: str, severity: str, message: str, details: dict[str, Any] | None = None
    ) -> None:
        async with self._db.session() as session:
            session.add(
                RiskEventRow(
                    kind=kind,
                    severity=severity,
                    message=message,
                    details=details or {},
                    occurred_at=datetime.now(UTC),
                )
            )

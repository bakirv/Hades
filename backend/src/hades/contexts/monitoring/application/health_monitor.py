"""Health Monitor — assembles system health from probes and reacts to changes.

On each pass it runs every registered probe, folds the results into a
:class:`SystemHealth`, persists the outcome (optional), updates metrics, and — on
a *transition* (healthy→degraded/unhealthy or back) — emits a domain event and
requests a notification. It never spams: notifications fire only when the overall
status changes, not on every identical pass.
"""

from __future__ import annotations

import asyncio

from hades.contexts.monitoring.domain.events import HealthDegraded, HealthRecovered
from hades.contexts.monitoring.domain.models import (
    ComponentHealth,
    HealthStatus,
    SystemHealth,
)
from hades.contexts.monitoring.domain.ports import HealthProbe
from hades.contexts.monitoring.infrastructure.repository import MonitoringRepository
from hades.contexts.notification.application.publisher import NotificationPublisher
from hades.contexts.notification.domain.ports import Severity
from hades.shared_kernel.domain.identifiers import new_id
from hades.shared_kernel.events import EventBus
from hades.shared_kernel.logging import get_logger
from hades.shared_kernel.observability import MetricsRegistry

_logger = get_logger("monitoring")


class HealthMonitor:
    """Runs probes, publishes health, and alerts on status transitions."""

    def __init__(
        self,
        probes: list[HealthProbe],
        *,
        event_bus: EventBus,
        metrics: MetricsRegistry,
        repository: MonitoringRepository | None = None,
        notifier: NotificationPublisher | None = None,
    ) -> None:
        self._probes = probes
        self._bus = event_bus
        self._metrics = metrics
        self._repo = repository
        self._notifier = notifier
        self._last_status: HealthStatus | None = None
        self._gauge = metrics.gauge(
            "hades_component_up", "1 if a component is healthy, else 0", ("component",)
        )
        self._system_gauge = metrics.gauge(
            "hades_system_health", "System health (2=healthy,1=degraded,0=unhealthy)"
        )

    async def run_once(self) -> SystemHealth:
        components = await asyncio.gather(*(self._safe_check(p) for p in self._probes))
        health = SystemHealth.from_components(list(components))
        self._export_metrics(health)

        if self._repo is not None:
            try:
                await self._repo.record_health(health)
            except Exception as exc:  # persistence must not break probing
                _logger.error("health_persist_failed", error=str(exc))

        await self._handle_transition(health)
        self._last_status = health.status
        return health

    async def _safe_check(self, probe: HealthProbe) -> ComponentHealth:
        try:
            return await probe.check()
        except Exception as exc:  # a probe error is an unhealthy result
            _logger.error("probe_raised", probe=probe.name, error=str(exc))
            return ComponentHealth(name=probe.name, status=HealthStatus.UNHEALTHY, detail=str(exc))

    def _export_metrics(self, health: SystemHealth) -> None:
        for component in health.components:
            up = 1.0 if component.status is HealthStatus.HEALTHY else 0.0
            self._gauge.labels(component=component.name).set(up)
        score = {
            HealthStatus.HEALTHY: 2.0,
            HealthStatus.DEGRADED: 1.0,
            HealthStatus.UNHEALTHY: 0.0,
        }[health.status]
        self._system_gauge.set(score)

    async def _handle_transition(self, health: SystemHealth) -> None:
        if health.status is self._last_status:
            return

        degraded_names = [c.name for c in health.components if c.status is not HealthStatus.HEALTHY]
        if health.status is HealthStatus.HEALTHY and self._last_status is not None:
            _logger.info("health_recovered")
            await self._bus.publish(HealthRecovered(aggregate_id=new_id()))
            await self._notify("System recovered", "All components healthy again.", Severity.INFO)
        elif health.status is not HealthStatus.HEALTHY:
            _logger.warning("health_degraded", status=health.status, components=degraded_names)
            await self._bus.publish(HealthDegraded(aggregate_id=new_id(), health=health))
            severity = (
                Severity.CRITICAL if health.status is HealthStatus.UNHEALTHY else Severity.WARNING
            )
            await self._notify(
                f"System {health.status.value}",
                "Affected: " + ", ".join(degraded_names),
                severity,
            )

    async def _notify(self, title: str, body: str, severity: Severity) -> None:
        if self._notifier is None:
            return
        try:
            await self._notifier.notify(
                title=title, body=body, severity=severity, tags={"topic": "health"}
            )
        except Exception as exc:
            _logger.error("health_notify_failed", error=str(exc))

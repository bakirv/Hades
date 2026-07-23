"""Domain events emitted by the Monitoring context."""

from __future__ import annotations

from hades.contexts.monitoring.domain.models import SystemHealth
from hades.shared_kernel.domain.events import DomainEvent


class ComponentHeartbeat(DomainEvent):
    """A component reported it is alive."""

    aggregate_type: str = "component"
    component: str


class HealthDegraded(DomainEvent):
    """Overall system health dropped below healthy."""

    aggregate_type: str = "system"
    health: SystemHealth


class HealthRecovered(DomainEvent):
    """Overall system health returned to healthy."""

    aggregate_type: str = "system"

"""Monitoring value objects (used by the live /health endpoint)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from hades.shared_kernel.domain.base import ValueObject


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ComponentHealth(ValueObject):
    """Health of one component or dependency."""

    name: str
    status: HealthStatus
    detail: str = ""


class SystemHealth(ValueObject):
    """Aggregate system health; ``status`` is the worst of its components."""

    status: HealthStatus
    components: list[ComponentHealth] = Field(default_factory=list)

    @classmethod
    def from_components(cls, components: list[ComponentHealth]) -> SystemHealth:
        if any(c.status is HealthStatus.UNHEALTHY for c in components):
            overall = HealthStatus.UNHEALTHY
        elif any(c.status is HealthStatus.DEGRADED for c in components):
            overall = HealthStatus.DEGRADED
        else:
            overall = HealthStatus.HEALTHY
        return cls(status=overall, components=components)

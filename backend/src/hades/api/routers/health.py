"""Health + readiness endpoints (consumed by Docker/K8s probes and the UI)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from hades.api.dependencies import get_container
from hades.bootstrap import Container
from hades.contexts.monitoring.domain.models import (
    ComponentHealth,
    HealthStatus,
    SystemHealth,
)
from hades.ops.preflight import DeploymentValidator, build_production_checklist

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness + aggregate system health")
async def health(
    response: Response, container: Container = Depends(get_container)
) -> dict[str, object]:
    """Return aggregate health. In Phase 1 the process itself is the only probe;
    dependency probes (db/redis/rpc) register here as they are wired."""
    components = [
        ComponentHealth(name="api", status=HealthStatus.HEALTHY, detail="process alive"),
    ]
    system = SystemHealth.from_components(components)
    if system.status is HealthStatus.UNHEALTHY:
        response.status_code = 503
    return {
        "status": system.status,
        "instance_id": container.settings.instance_id,
        "trading_mode": container.settings.trading_mode,
        "is_live": container.settings.is_live,
        "components": [c.model_dump() for c in system.components],
    }


@router.get("/ready", summary="Readiness probe")
async def ready() -> dict[str, str]:
    return {"status": "ready"}


@router.get("/health/preflight", summary="Deployment validation (config/deps/schema)")
async def preflight(container: Container = Depends(get_container)) -> dict[str, object]:
    """Run the deployment validator on demand (same checks as ``hades-preflight``)."""
    report = await DeploymentValidator(container).validate()
    return report.as_dict()


@router.get("/health/production-checklist", summary="Pre-LIVE readiness of every subsystem")
async def production_checklist(
    response: Response, container: Container = Depends(get_container)
) -> dict[str, object]:
    """The aggregated pre-LIVE checklist. ``ready`` is false — and LIVE stays
    blocked — if any required subsystem fails or Emergency Mode is active."""
    report = await build_production_checklist(container).report()
    if not report["ready"]:
        response.status_code = 503
    return report

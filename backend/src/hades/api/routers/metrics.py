"""Prometheus metrics exposition + performance snapshot endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from prometheus_client import CONTENT_TYPE_LATEST

from hades.api.dependencies import get_container
from hades.bootstrap import Container
from hades.ops.performance_runtime import PERFORMANCE_NAMESPACE, STATUS_KEY
from hades.shared_kernel.cache import CacheService

router = APIRouter(tags=["observability"])


@router.get("/metrics", summary="Prometheus metrics")
async def metrics(container: Container = Depends(get_container)) -> Response:
    return Response(
        content=container.metrics.render(),
        media_type=CONTENT_TYPE_LATEST,
    )


@router.get("/api/v1/metrics/performance", summary="Performance snapshot (latency + throughput)")
async def performance(container: Container = Depends(get_container)) -> dict[str, object]:
    """Latency (analysis/decision/execution/confirmation) and throughput
    (tokens/min, features/sec, predictions/min, ops/hour), published by the
    Worker's Performance Monitor. Returns ``available: false`` until the first
    snapshot is published."""
    cache = CacheService(container.redis, namespace=PERFORMANCE_NAMESPACE)
    snapshot = await cache.get(STATUS_KEY)
    if snapshot is None:
        return {"available": False}
    return {"available": True, **snapshot}

"""The API boots and its health/meta endpoints answer."""

from __future__ import annotations

from fastapi.testclient import TestClient

from hades.api.app import create_app


def test_health_endpoint() -> None:
    with TestClient(create_app()) as client:
        resp = client.get("/health")
        # Liveness answers 200 whatever the dependencies are doing: this endpoint
        # is Docker's restart trigger, and a Redis blip must not recycle a
        # perfectly healthy API. Dependency state is reported, not enforced here.
        assert resp.status_code == 200
        body = resp.json()
        # Safety: a fresh, unconfigured instance must never report live trading.
        assert body["is_live"] is False

        components = {c["name"]: c for c in body["components"]}
        assert components["api"]["status"] == "healthy"


def test_health_reports_dependencies_and_processes_not_just_itself() -> None:
    # The old endpoint hardcoded a single "api" component, so the page read
    # "healthy" even with Postgres, Redis and the Worker all down.
    with TestClient(create_app()) as client:
        components = {c["name"]: c for c in client.get("/health").json()["components"]}

    assert "redis" in components
    # Background processes are reported from their heartbeat files. None runs in
    # a test process, and "not deployed here" must read as unknown, not as broken.
    assert components["worker"]["status"] == "unknown"
    assert "no heartbeat file" in components["worker"]["detail"]


def test_readiness_gates_on_dependencies_unlike_liveness() -> None:
    with TestClient(create_app()) as client:
        resp = client.get("/ready")

    # No Redis/Postgres in a bare test process, so readiness must refuse traffic
    # even though liveness stays 200.
    assert resp.status_code == 503
    assert resp.json()["status"] == "not_ready"


def test_meta_lists_contexts() -> None:
    with TestClient(create_app()) as client:
        resp = client.get("/api/v1/meta")
        assert resp.status_code == 200
        body = resp.json()
        assert "scanner" in body["contexts"]
        assert "execution" in body["contexts"]
        assert body["version"]

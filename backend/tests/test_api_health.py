"""The API boots and its health/meta endpoints answer."""

from __future__ import annotations

from fastapi.testclient import TestClient

from hades.api.app import create_app


def test_health_endpoint() -> None:
    with TestClient(create_app()) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] in {"healthy", "degraded"}
        # Safety: a fresh, unconfigured instance must never report live trading.
        assert body["is_live"] is False


def test_meta_lists_contexts() -> None:
    with TestClient(create_app()) as client:
        resp = client.get("/api/v1/meta")
        assert resp.status_code == 200
        body = resp.json()
        assert "scanner" in body["contexts"]
        assert "execution" in body["contexts"]
        assert body["version"]

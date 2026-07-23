"""Strategy API endpoints: shape + degrade gracefully without Redis/DB."""

from __future__ import annotations

from fastapi.testclient import TestClient

from hades.api.app import create_app


def test_strategy_status_shape() -> None:
    with TestClient(create_app()) as client:
        body = client.get("/api/v1/strategies/status").json()
        assert "enabled" in body
        assert "running" in body
        assert "live" in body
        # The strategy surface never exposes orders or executed-trade info.
        assert "orders" not in body


def test_strategy_read_endpoints_render_without_state() -> None:
    with TestClient(create_app()) as client:
        assert "strategies" in client.get("/api/v1/strategies").json()
        assert "ranking" in client.get("/api/v1/strategies/ranking").json()
        assert "weights" in client.get("/api/v1/strategies/weights").json()
        assert "performance" in client.get("/api/v1/strategies/performance").json()
        assert "shadow" in client.get("/api/v1/strategies/shadow").json()
        assert "signals" in client.get("/api/v1/strategies/signals").json()
        assert "ensembles" in client.get("/api/v1/strategies/ensembles").json()

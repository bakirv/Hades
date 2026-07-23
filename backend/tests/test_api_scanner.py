"""Scanner API endpoint: shape + degrades gracefully without Redis/DB."""

from __future__ import annotations

from fastapi.testclient import TestClient

from hades.api.app import create_app


def test_scanner_status_shape() -> None:
    with TestClient(create_app()) as client:
        body = client.get("/api/v1/scanner/status").json()
        # Discovery-only fields — never risk/scoring.
        assert "enabled" in body
        assert "running" in body
        assert "configured_sources" in body
        assert "tokens_total" in body
        assert "anomalies_total" in body
        assert "live" in body
        # No risk information is exposed by the scanner surface.
        assert "risk" not in body
        assert "score" not in body

"""Security API endpoints: shape + graceful degradation without Redis/DB."""

from __future__ import annotations

from fastapi.testclient import TestClient

from hades.api.app import create_app


def test_security_status_shape() -> None:
    with TestClient(create_app()) as client:
        body = client.get("/api/v1/security/status").json()
        assert "enabled" in body
        assert "running" in body
        assert "min_security_score" in body
        assert "assessments_total" in body
        assert "approved_total" in body
        assert "rejected_total" in body
        assert "avg_security_score" in body
        assert "live" in body


def test_security_token_not_found_without_db() -> None:
    with TestClient(create_app()) as client:
        resp = client.get("/api/v1/security/token/" + "A" * 44)
        # No database in the test process → 503; with a DB but no row → 404.
        assert resp.status_code in (404, 503)


def test_security_rejections_and_lists_render() -> None:
    with TestClient(create_app()) as client:
        assert "rejections" in client.get("/api/v1/security/rejections").json()
        lists = client.get("/api/v1/security/lists").json()
        assert "blacklist" in lists
        assert "whitelist" in lists

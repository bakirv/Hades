"""Phase 2 API surface: status/version/info/config/trading + terminal WS."""

from __future__ import annotations

from fastapi.testclient import TestClient

from hades.api.app import create_app


def test_meta_endpoints_answer() -> None:
    with TestClient(create_app()) as client:
        assert client.get("/api/v1/version").json()["name"] == "hades"
        info = client.get("/api/v1/info").json()
        assert "engine" in info["services"]
        assert "scanner" in info["contexts"]


def test_status_reports_paper_and_not_live() -> None:
    with TestClient(create_app()) as client:
        body = client.get("/api/v1/status").json()
        assert body["role"] == "api"
        assert body["is_live"] is False
        assert body["uptime_seconds"] >= 0


def test_config_never_leaks_secrets() -> None:
    with TestClient(create_app()) as client:
        cfg = client.get("/api/v1/config").json()
        # Only presence flags for secrets, never the values.
        assert "discord_webhook_configured" in cfg["notifications"]
        assert "discord_webhook_url" not in cfg["notifications"]


def test_trading_mode_endpoint() -> None:
    with TestClient(create_app()) as client:
        body = client.get("/api/v1/trading/mode").json()
        assert body["mode"] == "paper"
        assert body["is_live"] is False


def test_switch_to_live_is_rejected_for_the_implicit_system_principal() -> None:
    # With global API auth off (the default), the caller is the implicit,
    # unauthenticated `system` principal. A switch to LIVE must be refused with
    # 403 before any readiness logic runs — the go-live action always requires a
    # real operator. Paper switches remain allowed.
    with TestClient(create_app()) as client:
        resp = client.post("/api/v1/trading/mode", json={"mode": "live", "confirm": True})
        assert resp.status_code == 403
        assert resp.json()["error"] == "PermissionDeniedError"


def test_terminal_websocket_streams_snapshot() -> None:
    with TestClient(create_app()) as client, client.websocket_connect("/ws/terminal") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "snapshot"
        assert isinstance(msg["records"], list)

"""Wallet Intelligence API: shape + graceful degradation without Redis/DB."""

from __future__ import annotations

from fastapi.testclient import TestClient

from hades.api.app import create_app


def test_intelligence_status_shape() -> None:
    with TestClient(create_app()) as client:
        body = client.get("/api/v1/intelligence/status").json()
        assert "enabled" in body
        assert "running" in body
        assert "wallets_total" in body
        assert "smart_money_total" in body
        assert "clusters_total" in body
        assert "live" in body


def test_intelligence_wallet_not_found_without_db() -> None:
    with TestClient(create_app()) as client:
        resp = client.get("/api/v1/intelligence/wallet/" + "A" * 44)
        assert resp.status_code in (404, 503)


def test_intelligence_collections_render() -> None:
    with TestClient(create_app()) as client:
        assert "clusters" in client.get("/api/v1/intelligence/clusters").json()
        assert "wallets" in client.get("/api/v1/intelligence/smart-money").json()
        timeline = client.get("/api/v1/intelligence/wallet/" + "A" * 44 + "/timeline").json()
        assert "timeline" in timeline
        rels = client.get("/api/v1/intelligence/wallet/" + "A" * 44 + "/relationships").json()
        assert "relationships" in rels

"""The expanded configuration exposes every Phase 2 section with sane defaults."""

from __future__ import annotations

from hades.shared_kernel.config import get_settings


def test_new_sections_present() -> None:
    s = get_settings()
    # Every Phase 2 concern is a typed, nested settings slice.
    assert s.dashboard.port == 5173
    assert s.scheduler.enabled is True
    assert s.backup.directory
    assert s.logging.directory
    assert s.feature.enabled is True
    assert s.learning.models_path
    assert s.research.datasets_path
    assert s.timeouts.rpc_seconds > 0
    assert s.paths.models


def test_wallet_not_configured_by_default() -> None:
    s = get_settings()
    assert s.wallet.is_configured is False


def test_watchdog_watched_roles_parse() -> None:
    s = get_settings()
    assert "worker" in s.watchdog.watched_role_list
    assert "notification" in s.watchdog.watched_role_list


def test_live_is_gated_off_by_default() -> None:
    s = get_settings()
    assert s.is_live is False


def test_the_connection_pools_fit_inside_a_stock_postgres() -> None:
    """Pool sizing is a fleet decision, not a per-process one.

    Six services (api, engine, worker, scheduler, notification, watchdog) each
    open their own pool against the same server. The defaults used to allow
    6 x (10 + 20) = 180 connections against a stock ``max_connections`` of 100:
    under load the server refused new clients, the health probe's SELECT 1
    failed, the watchdog reconnected successfully, and the cycle repeated every
    twenty seconds — reported to the operator as "component_recovered".
    """
    s = get_settings()
    services_with_a_pool = 6
    stock_max_connections = 100
    per_process = s.postgres.pool_size + s.postgres.max_overflow

    assert per_process * services_with_a_pool < stock_max_connections

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

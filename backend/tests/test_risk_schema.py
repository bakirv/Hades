"""The risk/portfolio schema is declared and the config maps from settings."""

from __future__ import annotations

import hades.shared_kernel.persistence.models  # noqa: F401  (registers tables)
from hades.contexts.risk.application.factory import risk_config_from_settings
from hades.shared_kernel.config import Settings
from hades.shared_kernel.config.settings import RiskSettings
from hades.shared_kernel.persistence.database import Base


def test_risk_tables_declared() -> None:
    tables = set(Base.metadata.tables)
    assert "risk_decisions" in tables
    assert "risk_control_state" in tables


def test_risk_tables_follow_platform_rule() -> None:
    for name in ("risk_decisions", "risk_control_state"):
        cols = Base.metadata.tables[name].columns
        assert "id" in cols and "created_at" in cols and "updated_at" in cols


def test_risk_config_from_settings_defaults() -> None:
    cfg = risk_config_from_settings(Settings())
    # Conservative defaults survive the mapping.
    assert cfg.sizing.min_prob_roi_positive == 0.55
    assert cfg.exposure.max_portfolio_pct == 50.0
    assert cfg.rates.max_concurrent_positions == 5
    assert cfg.kill_switch.consecutive_losses_halt == 5
    assert cfg.drawdown.daily_max_loss_usd == 200.0
    # Stop-loss flows from the position section into sizing.
    assert cfg.sizing.stop_loss_pct == Settings().position.default_stop_loss_pct


def test_budget_map_parses() -> None:
    allocations = RiskSettings(risk_budget_map="momentum:25,swing:40").budget_allocations
    assert allocations["momentum"] == 25.0
    assert allocations["swing"] == 40.0
    assert RiskSettings(risk_budget_map="").budget_allocations == {}

"""The pure risk engines size and cap correctly, and degrade safely."""

from __future__ import annotations

from datetime import UTC, datetime

from hades.contexts.common.domain.value_objects import TokenMint, TokenRef
from hades.contexts.risk.application.correlation import CorrelationEngine
from hades.contexts.risk.application.drawdown import DrawdownEngine
from hades.contexts.risk.application.exposure import ExposureEngine
from hades.contexts.risk.application.risk_budget import RiskBudgetEngine
from hades.contexts.risk.application.sizing import PositionSizingEngine
from hades.contexts.risk.domain.models import (
    CapitalSnapshot,
    DrawdownLimits,
    DrawdownSnapshot,
    ExposureAxis,
    ExposureLimits,
    OpenPositionView,
    PortfolioRiskState,
    RiskBudget,
    RiskCandidate,
    SizingConfig,
)

_MINTS = [
    "So11111111111111111111111111111111111111112",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
]


def _token(i: int = 0) -> TokenRef:
    return TokenRef(mint=TokenMint(address=_MINTS[i]), symbol=f"T{i}")


def _candidate(**over: object) -> RiskCandidate:
    base: dict[str, object] = {
        "token": _token(0),
        "at": datetime.now(UTC),
        "prob_roi_positive": 0.8,
        "prob_hit_tp": 0.7,
        "prob_hit_sl": 0.3,
        "confidence": 0.9,
        "security_score": 90.0,
        "liquidity_score": 80.0,
        "wallet_risk_score": 20.0,
        "regime": "bull",
    }
    base.update(over)
    return RiskCandidate(**base)  # type: ignore[arg-type]


def _capital(equity: float = 1000.0, cash: float | None = None) -> CapitalSnapshot:
    return CapitalSnapshot(
        equity_usd=equity,
        cash_usd=cash if cash is not None else equity,
        invested_usd=0.0,
        reserve_pct=0.0,
    )


def _state(positions: tuple[OpenPositionView, ...] = (), **cap: float) -> PortfolioRiskState:
    return PortfolioRiskState(capital=_capital(**cap), open_positions=positions)


# -- sizing --------------------------------------------------------------------


def test_sizing_scales_with_conviction() -> None:
    engine = PositionSizingEngine(SizingConfig(max_position_size_usd=1000.0))
    strong = engine.size(_candidate(), equity_usd=1000.0, available_usd=1000.0)
    weak = engine.size(
        _candidate(prob_roi_positive=0.56, confidence=0.45, security_score=62, liquidity_score=55),
        equity_usd=1000.0,
        available_usd=1000.0,
    )
    assert strong.approved and weak.approved
    assert strong.sizing is not None and weak.sizing is not None
    assert float(strong.sizing.notional.amount) > float(weak.sizing.notional.amount)


def test_sizing_rejects_below_minimum() -> None:
    engine = PositionSizingEngine(SizingConfig(min_position_size_usd=50.0))
    # Tiny equity -> notional below the floor.
    result = engine.size(_candidate(), equity_usd=10.0, available_usd=10.0)
    assert result.approved is False


def test_sizing_respects_kill_switch_factor() -> None:
    engine = PositionSizingEngine(SizingConfig(max_position_size_usd=1000.0))
    full = engine.size(
        _candidate(), equity_usd=1000.0, available_usd=1000.0, kill_switch_factor=1.0
    )
    halved = engine.size(
        _candidate(), equity_usd=1000.0, available_usd=1000.0, kill_switch_factor=0.5
    )
    assert full.sizing is not None and halved.sizing is not None
    assert float(halved.sizing.notional.amount) < float(full.sizing.notional.amount)


def test_sizing_bounded_by_available_capital() -> None:
    engine = PositionSizingEngine(SizingConfig(max_position_size_usd=1_000_000.0))
    result = engine.size(_candidate(), equity_usd=100_000.0, available_usd=5.0)
    assert result.sizing is not None
    assert float(result.sizing.notional.amount) <= 5.0


# -- exposure ------------------------------------------------------------------


def test_exposure_breakdown_by_token() -> None:
    pos = OpenPositionView(token=_token(0), notional_usd=200.0)
    state = _state((pos,), equity=1000.0)
    engine = ExposureEngine(ExposureLimits())
    breakdown = engine.breakdown(state, ExposureAxis.TOKEN)
    assert breakdown.pct_for(str(_token(0).mint)) == 20.0


def test_exposure_check_flags_developer_concentration() -> None:
    pos = OpenPositionView(token=_token(0), notional_usd=200.0, developer="devX")
    state = _state((pos,), equity=1000.0)
    engine = ExposureEngine(ExposureLimits(per_developer_pct=25.0))
    cand = _candidate(token=_token(1), developer="devX")
    breach = engine.check(cand, state, proposed_notional_usd=100.0)  # 20% + 10% = 30% > 25%
    assert breach is not None
    assert breach.axis is ExposureAxis.DEVELOPER


def test_exposure_check_none_when_within_caps() -> None:
    state = _state((), equity=1000.0)
    engine = ExposureEngine(ExposureLimits())
    assert engine.check(_candidate(), state, proposed_notional_usd=50.0) is None


# -- correlation ---------------------------------------------------------------


def test_correlation_counts_shared_narrative() -> None:
    positions = (
        OpenPositionView(token=_token(0), notional_usd=100.0, narrative="dogs"),
        OpenPositionView(token=_token(1), notional_usd=100.0, narrative="dogs"),
    )
    state = _state(positions, equity=1000.0)
    engine = CorrelationEngine(max_correlated=2)
    cand = _candidate(token=_token(2), narrative="dogs")
    assert engine.correlation_count(cand, state) == 2
    assert engine.is_overcorrelated(cand, state) is True


def test_correlation_ignores_unrelated() -> None:
    positions = (OpenPositionView(token=_token(0), notional_usd=100.0, narrative="cats"),)
    state = _state(positions, equity=1000.0)
    engine = CorrelationEngine(max_correlated=3)
    assert engine.is_overcorrelated(_candidate(narrative="dogs"), state) is False


# -- drawdown ------------------------------------------------------------------


def test_drawdown_daily_breach() -> None:
    engine = DrawdownEngine(DrawdownLimits(daily_pct=10.0, daily_max_loss_usd=0.0))
    dd = DrawdownSnapshot(peak_equity_usd=1000.0, current_equity_usd=880.0, daily_pnl_usd=-120.0)
    breach = engine.evaluate(dd)
    assert breach is not None and breach.window == "daily"


def test_drawdown_absolute_usd_breach() -> None:
    engine = DrawdownEngine(DrawdownLimits(daily_max_loss_usd=100.0))
    dd = DrawdownSnapshot(peak_equity_usd=1000.0, current_equity_usd=880.0, daily_pnl_usd=-120.0)
    breach = engine.evaluate(dd)
    assert breach is not None and breach.window == "daily_usd"


def test_drawdown_stop_limit() -> None:
    engine = DrawdownEngine(DrawdownLimits(daily_max_stop_losses=3))
    assert engine.stop_limit_breached(DrawdownSnapshot(daily_stop_losses=3)) is True
    assert engine.stop_limit_breached(DrawdownSnapshot(daily_stop_losses=2)) is False


# -- risk budget ---------------------------------------------------------------


def test_risk_budget_blocks_over_slice() -> None:
    engine = RiskBudgetEngine(RiskBudget(allocations={"momentum": 25.0}))
    pos = OpenPositionView(token=_token(0), notional_usd=200.0, strategy="momentum")
    state = _state((pos,), equity=1000.0)  # momentum already 20%
    exceeds, projected, budget = engine.would_exceed(state, "momentum", proposed_notional_usd=100.0)
    assert exceeds is True and budget == 25.0 and projected == 30.0


def test_risk_budget_unconfigured_allows_all() -> None:
    engine = RiskBudgetEngine(RiskBudget())
    state = _state((), equity=1000.0)
    exceeds, _, budget = engine.would_exceed(state, "anything", proposed_notional_usd=500.0)
    assert exceeds is False and budget == 100.0

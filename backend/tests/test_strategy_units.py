"""Unit tests for the Strategy Engine building blocks.

Covers the plugins (metadata + evaluation), the dynamic-weighting factors, the
weighted ensemble fusion (never a simple vote), the self-evaluation statistics,
the shadow lifecycle rules and the market-context builder.
"""

from __future__ import annotations

from datetime import UTC, datetime

from hades.contexts.common.domain.value_objects import TokenMint, TokenRef
from hades.contexts.learning.domain.models import (
    CommitteeMember,
    CommitteePrediction,
    MarketRegime,
    MetaPrediction,
    Opinion,
    RegimeAssessment,
)
from hades.contexts.strategy.application.context_builder import MarketContextBuilder
from hades.contexts.strategy.application.ensemble import EnsembleBuilder
from hades.contexts.strategy.application.evaluation import SelfEvaluator
from hades.contexts.strategy.application.lifecycle import PromotionError, ShadowLifecycle
from hades.contexts.strategy.application.strategies import STRATEGY_TYPES, default_strategies
from hades.contexts.strategy.application.strategies.momentum_breakout import (
    MomentumBreakoutStrategy,
)
from hades.contexts.strategy.application.weighting import DynamicWeightEngine
from hades.contexts.strategy.domain.models import (
    LifecycleStage,
    MarketContext,
    SignalType,
    StrategyOutcome,
    StrategySignal,
    StrategyWeight,
)

_TOKEN = TokenRef(mint=TokenMint(address="M" * 44), symbol="MEME")


def _ctx(
    *,
    regime: MarketRegime = MarketRegime.BULL,
    members: dict[str, float] | None = None,
    tp: float = 0.5,
    sl: float = 0.5,
    ai_confidence: float = 0.7,
    **kwargs: object,
) -> MarketContext:
    return MarketContext(
        token=_TOKEN,
        regime=regime,
        member_scores=members or {},
        ai_prob_hit_tp=tp,
        ai_prob_hit_sl=sl,
        ai_confidence=ai_confidence,
        **kwargs,  # type: ignore[arg-type]
    )


# --- roster ------------------------------------------------------------------


def test_ships_fifteen_unique_strategies() -> None:
    strategies = default_strategies()
    assert len(strategies) == 15
    assert len(STRATEGY_TYPES) == 15
    names = {s.metadata.name for s in strategies}
    assert len(names) == 15  # every name is unique


def test_every_strategy_exposes_full_metadata() -> None:
    for strategy in default_strategies():
        meta = strategy.metadata
        assert meta.name
        assert meta.version
        assert meta.description
        assert meta.features_used  # declares the features it consumes
        assert meta.priority >= 1


# --- plugin behaviour --------------------------------------------------------


def test_momentum_breakout_buys_on_strong_momentum() -> None:
    strategy = MomentumBreakoutStrategy()
    signal = strategy.generate_signal(
        _ctx(members={"momentum": 82, "volatility": 60, "microstructure": 60}, tp=0.72, sl=0.28)
    )
    assert signal.signal_type is SignalType.BUY
    assert signal.internal_score > 0.5
    assert signal.explanation.drivers  # never a bare number
    assert signal.reasoning


def test_momentum_breakout_ignores_when_weak() -> None:
    strategy = MomentumBreakoutStrategy()
    signal = strategy.generate_signal(_ctx(members={"momentum": 25}, tp=0.5, sl=0.5))
    assert signal.signal_type is SignalType.IGNORE


def test_forbidden_regime_blocks_the_signal() -> None:
    strategy = MomentumBreakoutStrategy()  # forbids PANIC / BEAR
    signal = strategy.generate_signal(
        _ctx(regime=MarketRegime.PANIC, members={"momentum": 90}, tp=0.9, sl=0.1)
    )
    assert signal.signal_type is SignalType.IGNORE
    validation = strategy.validate_market(_ctx(regime=MarketRegime.PANIC))
    assert validation.ok is False


def test_configuration_can_disable_and_tune_a_strategy() -> None:
    strategy = MomentumBreakoutStrategy()
    strategy.load_configuration({"enabled": False, "sensitivity": 2.0})
    assert strategy.metadata.status.value == "disabled"
    assert strategy.sensitivity == 2.0


# --- weighting ---------------------------------------------------------------


def test_weight_is_dynamic_by_regime_and_floored() -> None:
    engine = DynamicWeightEngine(weight_floor=0.05)
    strategy = MomentumBreakoutStrategy()  # ideal BULL/FOMO, forbids PANIC
    in_bull = engine.compute(strategy, _ctx(regime=MarketRegime.BULL), None)
    in_panic = engine.compute(strategy, _ctx(regime=MarketRegime.PANIC), None)
    assert in_bull.weight > in_panic.weight  # regime changes the weight
    assert in_panic.weight >= 0.05  # never zero — muted, never removed
    assert in_bull.regime_factor > 1.0
    assert in_bull.reason  # legible decomposition


# --- ensemble ----------------------------------------------------------------


def _sig(
    name: str,
    signal_type: SignalType,
    *,
    confidence: float = 0.9,
    score: float = 0.9,
    shadow: bool = False,
) -> StrategySignal:
    return StrategySignal(
        strategy=name,
        token=_TOKEN,
        signal_type=signal_type,
        confidence=confidence,
        internal_score=score,
        shadow=shadow,
    )


def _w(name: str, weight: float) -> StrategyWeight:
    return StrategyWeight(strategy=name, weight=weight)


def test_ensemble_is_weighted_not_a_vote() -> None:
    builder = EnsembleBuilder(decision_deadband=0.1)
    signals = [_sig("a", SignalType.BUY), _sig("b", SignalType.EXIT)]
    weights = {"a": _w("a", 3.0), "b": _w("b", 0.3)}  # heavy BUY, light EXIT
    ensemble = builder.build(_ctx(), signals, weights)
    # A simple vote would tie 1-1; the weight makes it a clear BUY.
    assert ensemble.decision is SignalType.BUY
    assert ensemble.score > 0
    assert ensemble.participating == 2
    assert len(ensemble.contributions) == 2


def test_ensemble_excludes_shadow_strategies_from_the_decision() -> None:
    builder = EnsembleBuilder(decision_deadband=0.1)
    signals = [_sig("prod", SignalType.BUY), _sig("shadow", SignalType.EXIT, shadow=True)]
    weights = {"prod": _w("prod", 1.0), "shadow": _w("shadow", 5.0)}
    ensemble = builder.build(_ctx(), signals, weights)
    assert ensemble.decision is SignalType.BUY  # shadow's heavy EXIT is ignored
    assert ensemble.participating == 1
    # …but the shadow contribution is still recorded for observation.
    assert any(c.shadow for c in ensemble.contributions)


def test_ensemble_ignores_when_no_consensus() -> None:
    builder = EnsembleBuilder(decision_deadband=0.3)
    signals = [_sig("a", SignalType.BUY, score=0.2), _sig("b", SignalType.EXIT, score=0.2)]
    weights = {"a": _w("a", 1.0), "b": _w("b", 1.0)}
    ensemble = builder.build(_ctx(), signals, weights)
    assert ensemble.decision is SignalType.IGNORE


# --- self-evaluation ---------------------------------------------------------


def test_self_evaluation_computes_expected_metrics() -> None:
    evaluator = SelfEvaluator()
    outcomes = [
        StrategyOutcome(strategy="s", realized_pnl_usd=10.0, win=True),
        StrategyOutcome(strategy="s", realized_pnl_usd=-5.0),
        StrategyOutcome(strategy="s", realized_pnl_usd=20.0, win=True),
        StrategyOutcome(strategy="s", realized_pnl_usd=-5.0),
    ]
    perf = evaluator.evaluate("s", outcomes)
    assert perf.trades == 4
    assert perf.win_rate == 0.5
    assert perf.profit_factor == 3.0  # 30 gross win / 10 gross loss
    assert perf.expectancy_usd == 5.0  # net 20 / 4 trades
    assert perf.net_pnl_usd == 20.0


def test_degradation_flag_lowers_weight() -> None:
    evaluator = SelfEvaluator(min_trades_for_degrade=3, degrade_profit_factor=1.0)
    losing = [StrategyOutcome(strategy="s", realized_pnl_usd=-1.0) for _ in range(5)]
    perf = evaluator.evaluate("s", losing)
    assert perf.degraded is True
    engine = DynamicWeightEngine()
    strong = engine.compute(MomentumBreakoutStrategy(), _ctx(regime=MarketRegime.BULL), None)
    weak = engine.compute(MomentumBreakoutStrategy(), _ctx(regime=MarketRegime.BULL), perf)
    assert weak.weight < strong.weight  # tapered, but…
    assert weak.weight >= 0.05  # …never removed


# --- lifecycle ---------------------------------------------------------------


def test_lifecycle_promotes_one_step_and_rejects_skips() -> None:
    lifecycle = ShadowLifecycle()
    strategy = MomentumBreakoutStrategy()
    strategy.override_metadata(lifecycle_stage=LifecycleStage.RESEARCH)
    previous, new = lifecycle.promote(strategy)
    assert previous is LifecycleStage.RESEARCH
    assert new is LifecycleStage.BACKTEST
    # A two-rung jump is illegal.
    try:
        lifecycle.set_stage(strategy, LifecycleStage.PAPER)
    except PromotionError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected a PromotionError on a skip")


def test_below_production_is_shadow() -> None:
    lifecycle = ShadowLifecycle()
    assert lifecycle.is_shadow(LifecycleStage.SHADOW) is True
    assert lifecycle.is_shadow(LifecycleStage.PRODUCTION) is False


# --- context builder ---------------------------------------------------------


async def test_context_builder_maps_committee_opinions() -> None:
    prediction = CommitteePrediction(
        token=_TOKEN,
        at=datetime.now(UTC),
        meta=MetaPrediction(
            token=_TOKEN,
            prob_roi_positive=0.7,
            prob_hit_tp=0.6,
            prob_hit_sl=0.2,
            confidence=0.8,
        ),
        opinions=(
            Opinion(member=CommitteeMember.MOMENTUM, probability=0.8, confidence=0.9),
            Opinion(member=CommitteeMember.WALLET, probability=0.6, confidence=0.7),
        ),
        regime=RegimeAssessment(regime=MarketRegime.BULL, confidence=0.75),
    )
    context = await MarketContextBuilder().from_prediction(prediction)
    assert context.regime is MarketRegime.BULL
    assert context.member("momentum") == 80.0  # probability * 100
    assert context.wallet_score == 60.0
    assert context.ai_expected_edge == 0.4

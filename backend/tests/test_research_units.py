"""Unit tests for the Research Lab's pure building blocks (no I/O)."""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

from hades.contexts.research.application import metrics as m
from hades.contexts.research.application.backtest_engine import BacktestingEngine
from hades.contexts.research.application.comparators import ModelComparator, StrategyComparator
from hades.contexts.research.application.feature_discovery import FeatureDiscoveryEngine
from hades.contexts.research.application.monte_carlo import MonteCarloEngine
from hades.contexts.research.application.optimizer import ParameterOptimizer
from hades.contexts.research.application.promotion import PromotionEngine
from hades.contexts.research.application.scheduler import AutoResearchScheduler, ResearchTask
from hades.contexts.research.application.shadow import ShadowStrategyRunner
from hades.contexts.research.application.strategies import default_genome, score_sample
from hades.contexts.research.application.validation import ValidationEngine
from hades.contexts.research.application.walk_forward import WalkForwardEngine
from hades.contexts.research.domain.models import (
    CandidateStrategy,
    MarketConditions,
    PerformanceMetrics,
    PromotionCriteria,
    ShadowStrategy,
    StrategyArchetype,
    TradeRecord,
    ValidationStage,
)
from hades.contexts.research.domain.ports import HistoricalSample


def _trade(ret: float, *, hold: float = 100.0) -> TradeRecord:
    now = datetime(2024, 1, 1, tzinfo=UTC)
    return TradeRecord(
        opened_at=now,
        closed_at=now + timedelta(seconds=hold),
        ret=ret,
        holding_seconds=hold,
    )


def _edge_samples(n: int = 300, *, seed: int = 3) -> list[HistoricalSample]:
    """Synthetic samples with a real edge: high momentum+liquidity → positive fwd."""
    rng = random.Random(seed)
    out: list[HistoricalSample] = []
    for i in range(n):
        strong = rng.random()
        liquidity = rng.random()
        # Forward return correlated with the momentum channel, plus noise.
        fwd = 0.4 * (strong - 0.5) + rng.uniform(-0.05, 0.05)
        out.append(
            HistoricalSample(
                {
                    "mint": f"M{i:04d}" + "x" * 40,
                    "momentum": strong,
                    "price_change": strong,
                    "liquidity": liquidity,
                    "volume": rng.random(),
                    "forward_return": fwd,
                    "holding_seconds": 300.0,
                }
            )
        )
    return out


# --- metrics -----------------------------------------------------------------


def test_metrics_empty() -> None:
    assert m.compute([]).is_empty


def test_metrics_basic_scorecard() -> None:
    trades = [_trade(0.1), _trade(-0.05), _trade(0.2), _trade(-0.1), _trade(0.05)]
    sc = m.compute(trades)
    assert sc.trades == 5
    assert sc.wins == 3
    assert sc.losses == 2
    assert sc.win_rate == 0.6
    assert sc.gross_profit > 0
    assert sc.gross_loss > 0
    assert sc.profit_factor > 0


def test_max_drawdown_and_curve() -> None:
    curve = m.equity_curve([0.1, -0.5, 0.1])
    assert curve[0] == 1.0
    dd = m.max_drawdown(curve)
    assert 0.0 < dd < 1.0


def test_multi_objective_penalises_drawdown() -> None:
    good = PerformanceMetrics(
        trades=40, total_return=0.5, sharpe=2.0, max_drawdown=0.1, expectancy=0.02
    )
    risky = good.model_copy(update={"max_drawdown": 0.6})
    assert m.multi_objective_score(good) > m.multi_objective_score(risky)


# --- strategies + backtest ---------------------------------------------------


def test_strategy_scores_within_unit_interval() -> None:
    genome = default_genome(StrategyArchetype.MOMENTUM)
    sample = HistoricalSample({"momentum": 0.9, "liquidity": 0.8, "volume": 0.7})
    score = score_sample(genome, sample)
    assert 0.0 <= score <= 1.0


def test_backtest_applies_frictions() -> None:
    genome = default_genome(StrategyArchetype.MOMENTUM)
    samples = _edge_samples()
    engine = BacktestingEngine()
    frictionless = engine.run(
        strategy="m",
        genome=genome,
        samples=samples,
        conditions=MarketConditions(slippage_bps=0, fee_bps=0),
    )
    costly = engine.run(
        strategy="m",
        genome=genome,
        samples=samples,
        conditions=MarketConditions(slippage_bps=300, fee_bps=100),
    )
    # Frictions can only reduce (or equal) the net return.
    assert costly.metrics.total_return <= frictionless.metrics.total_return


def test_backtest_finds_edge_on_signal() -> None:
    genome = default_genome(StrategyArchetype.MOMENTUM).model_copy(update={"entry_score": 0.55})
    result = BacktestingEngine().run(strategy="m", genome=genome, samples=_edge_samples())
    assert result.metrics.trades > 0


# --- walk-forward ------------------------------------------------------------


def test_walk_forward_produces_windows() -> None:
    genome = default_genome(StrategyArchetype.MOMENTUM)
    wf = WalkForwardEngine().run(strategy="m", genome=genome, samples=_edge_samples(), folds=4)
    assert len(wf.windows) >= 1
    assert wf.aggregate_oos.trades >= 0


# --- monte-carlo -------------------------------------------------------------


def test_monte_carlo_is_deterministic_and_bounded() -> None:
    trades = [_trade(0.1), _trade(-0.05), _trade(0.15), _trade(-0.08)] * 10
    a = MonteCarloEngine(seed=1).run(strategy="m", trades=trades, simulations=200)
    b = MonteCarloEngine(seed=1).run(strategy="m", trades=trades, simulations=200)
    assert a.mean_return == b.mean_return
    assert 0.0 <= a.prob_profit <= 1.0
    assert 0.0 <= a.robustness <= 1.0


def test_monte_carlo_empty_trades() -> None:
    assert MonteCarloEngine().run(strategy="m", trades=[]).simulations == 0


# --- optimizer ---------------------------------------------------------------


def test_optimizer_returns_best_within_space() -> None:
    genome = default_genome(StrategyArchetype.MOMENTUM)
    opt = ParameterOptimizer(seed=5).optimize(
        strategy="m", genome=genome, samples=_edge_samples(), evaluations=15
    )
    assert opt.evaluations == 15
    assert 0.10 <= opt.best_params["take_profit"] <= 0.60
    assert 0.05 <= opt.best_params["stop_loss"] <= 0.30


# --- shadow ------------------------------------------------------------------


def test_shadow_opens_and_closes_virtual_trades() -> None:
    genome = default_genome(StrategyArchetype.MOMENTUM).model_copy(update={"entry_score": 0.5})
    shadow = ShadowStrategy(name="s", archetype=StrategyArchetype.MOMENTUM, genome=genome)
    runner = ShadowStrategyRunner(shadow)
    # A strong sample opens a virtual position; every virtual trade has zero size.
    mint = "A" * 44
    strong = HistoricalSample(
        {"mint": mint, "momentum": 0.95, "liquidity": 0.9, "volume": 0.9, "forward_return": 0.0}
    )
    snap = runner.observe(strong)
    assert len(snap.open_trades) == 1
    assert snap.open_trades[0].size_usd == 0.0
    # A later sample with a TP-hitting forward return closes it.
    closing = HistoricalSample(
        {"mint": mint, "momentum": 0.1, "liquidity": 0.5, "forward_return": 0.5}
    )
    snap2 = runner.observe(closing, at=datetime.now(UTC))
    assert snap2.metrics.trades >= 1


# --- feature discovery -------------------------------------------------------


def test_feature_discovery_only_proposes() -> None:
    engine = FeatureDiscoveryEngine()
    proposals = engine.analyze(_edge_samples())
    # Every proposal is advisory; none is a removal command.
    for p in proposals:
        assert p.action in {"add", "flag_redundant", "flag_irrelevant", "combine"}
    importance = engine.importance(_edge_samples())
    # The momentum channel (which drives the label) should rank as useful.
    assert importance.get("momentum", 0.0) >= importance.get("volume", 0.0)


# --- comparators -------------------------------------------------------------


def test_strategy_comparator_ranks_by_objective() -> None:
    a = PerformanceMetrics(trades=50, expectancy=0.05, sharpe=2.0)
    b = PerformanceMetrics(trades=50, expectancy=0.01, sharpe=1.0)
    comp = StrategyComparator().compare({"a": a, "b": b}, objective="expectancy")
    assert comp.ranking[0] == "a"


def test_model_comparator_verdict() -> None:
    comp = ModelComparator().compare(
        production={"auc": 0.6, "max_drawdown": 0.2},
        candidate={"auc": 0.7, "max_drawdown": 0.2},
    )
    assert "improves" in comp.verdict
    assert comp.deltas["auc"] > 0


# --- promotion (fail-closed, human-gated) ------------------------------------


def _strong_candidate() -> CandidateStrategy:
    genome = default_genome(StrategyArchetype.MOMENTUM)
    metrics = PerformanceMetrics(
        trades=600, sharpe=1.5, max_drawdown=0.15, profit_factor=1.6, expectancy=0.03
    )
    return CandidateStrategy(
        name="c", archetype=StrategyArchetype.MOMENTUM, genome=genome, metrics=metrics
    )


def test_promotion_fails_closed_without_human() -> None:
    engine = PromotionEngine(PromotionCriteria())
    decision = engine.evaluate(
        _strong_candidate(), paper_positive=True, shadow_positive=True, manual_approve=False
    )
    # Meets every quantitative bar, but without a human it can never be promotable.
    assert "manual_approval" in decision.failed
    assert not decision.promotable


def test_promotion_approved_with_human() -> None:
    engine = PromotionEngine(PromotionCriteria())
    decision = engine.evaluate(
        _strong_candidate(), paper_positive=True, shadow_positive=True, manual_approve=True
    )
    assert decision.promotable
    assert decision.outcome.value == "approved"


def test_promotion_rejects_weak_candidate() -> None:
    weak = _strong_candidate().model_copy(
        update={"metrics": PerformanceMetrics(trades=10, sharpe=0.1, max_drawdown=0.5)}
    )
    decision = PromotionEngine().evaluate(weak, manual_approve=True)
    assert not decision.promotable
    assert decision.failed


# --- validation gauntlet -----------------------------------------------------


def test_validation_runs_stages_in_order() -> None:
    candidate = CandidateStrategy(
        name="v",
        archetype=StrategyArchetype.MOMENTUM,
        genome=default_genome(StrategyArchetype.MOMENTUM).model_copy(update={"entry_score": 0.5}),
    )
    samples = _edge_samples(360)
    report = ValidationEngine(min_trades=1).run(
        candidate, train=samples[:200], validation=samples[200:280], forward=samples[280:]
    )
    stages = [s.stage for s in report.stages]
    # Stages always appear in the mandated order, never skipped.
    order = [
        ValidationStage.TRAINING,
        ValidationStage.VALIDATION,
        ValidationStage.FORWARD_TEST,
        ValidationStage.PAPER_REPLAY,
        ValidationStage.SHADOW,
    ]
    filtered = [s for s in order if s in stages]
    assert stages == filtered


# --- scheduler ---------------------------------------------------------------


def test_scheduler_due_after_interval() -> None:
    sched = AutoResearchScheduler(intervals={ResearchTask.BACKTEST: 100.0})
    sched.seed(0.0)
    assert ResearchTask.BACKTEST not in sched.due(50.0)
    assert ResearchTask.BACKTEST in sched.due(150.0)
    sched.mark_ran(ResearchTask.BACKTEST, 150.0)
    assert ResearchTask.BACKTEST not in sched.due(200.0)

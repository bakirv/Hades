"""Validation Engine — the one-way gauntlet every candidate must climb.

The mandated pipeline is::

    Training → Validation → Forward Test → Paper Replay → Shadow → Production

A candidate advances one stage at a time and **never skips**. Each stage has an
objective bar; failing a stage stops the ascent there. Reaching the top of this
engine means "eligible to be *recommended* for production" — it does not put
anything into production. That final move is the human-gated Promotion Engine.
"""

from __future__ import annotations

from collections.abc import Sequence

from hades.contexts.research.application.backtest_engine import BacktestingEngine
from hades.contexts.research.application.monte_carlo import MonteCarloEngine
from hades.contexts.research.application.strategies import evaluate
from hades.contexts.research.application.walk_forward import WalkForwardEngine
from hades.contexts.research.domain.models import (
    CandidateStrategy,
    PerformanceMetrics,
    ValidationStage,
)
from hades.contexts.research.domain.ports import HistoricalSample

# The immutable stage order — index defines "later than".
_ORDER: tuple[ValidationStage, ...] = (
    ValidationStage.TRAINING,
    ValidationStage.VALIDATION,
    ValidationStage.FORWARD_TEST,
    ValidationStage.PAPER_REPLAY,
    ValidationStage.SHADOW,
    ValidationStage.PRODUCTION,
)


class StageReport:
    """The outcome of attempting one stage (kept simple and printable)."""

    def __init__(
        self,
        stage: ValidationStage,
        passed: bool,
        detail: str,
        metrics: PerformanceMetrics,
    ) -> None:
        self.stage = stage
        self.passed = passed
        self.detail = detail
        self.metrics = metrics

    def as_dict(self) -> dict[str, object]:
        return {
            "stage": self.stage.value,
            "passed": self.passed,
            "detail": self.detail,
            "metrics": self.metrics.model_dump(mode="json"),
        }


class ValidationReport:
    """The full ascent record: how far a candidate climbed and why it stopped."""

    def __init__(self, candidate: CandidateStrategy) -> None:
        self.candidate = candidate
        self.stages: list[StageReport] = []

    @property
    def reached(self) -> ValidationStage:
        passed = [r.stage for r in self.stages if r.passed]
        return passed[-1] if passed else ValidationStage.TRAINING

    @property
    def eligible_for_production(self) -> bool:
        """True only if the SHADOW stage passed (the last gate before the human)."""
        return any(r.stage is ValidationStage.SHADOW and r.passed for r in self.stages)

    def as_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate.candidate_id,
            "name": self.candidate.name,
            "reached": self.reached.value,
            "eligible_for_production": self.eligible_for_production,
            "stages": [s.as_dict() for s in self.stages],
        }


class ValidationEngine:
    """Runs a candidate through the staged gauntlet, stopping at the first failure."""

    def __init__(
        self,
        *,
        backtester: BacktestingEngine | None = None,
        walk_forward: WalkForwardEngine | None = None,
        monte_carlo: MonteCarloEngine | None = None,
        min_trades: int = 30,
        min_profit_factor: float = 1.1,
        max_drawdown: float = 0.35,
        min_robustness: float = 0.5,
        min_wf_efficiency: float = 0.4,
    ) -> None:
        self._bt = backtester or BacktestingEngine()
        self._wf = walk_forward or WalkForwardEngine(self._bt)
        self._mc = monte_carlo or MonteCarloEngine()
        self._min_trades = min_trades
        self._min_pf = min_profit_factor
        self._max_dd = max_drawdown
        self._min_robustness = min_robustness
        self._min_wf_eff = min_wf_efficiency

    def run(
        self,
        candidate: CandidateStrategy,
        *,
        train: Sequence[HistoricalSample],
        validation: Sequence[HistoricalSample],
        forward: Sequence[HistoricalSample],
    ) -> ValidationReport:
        report = ValidationReport(candidate)
        genome = candidate.genome

        # 1) TRAINING — measurable edge on the training set.
        train_bt = self._bt.run(strategy=candidate.name, genome=genome, samples=train)
        ok = (
            train_bt.metrics.trades >= self._min_trades
            and train_bt.metrics.profit_factor >= self._min_pf
        )
        report.stages.append(
            StageReport(
                ValidationStage.TRAINING, ok, self._pf_detail(train_bt.metrics), train_bt.metrics
            )
        )
        if not ok:
            return report

        # 2) VALIDATION — holds up on a disjoint validation set.
        val_bt = self._bt.run(strategy=candidate.name, genome=genome, samples=validation)
        ok = (
            val_bt.metrics.profit_factor >= self._min_pf
            and val_bt.metrics.max_drawdown <= self._max_dd
        )
        report.stages.append(
            StageReport(
                ValidationStage.VALIDATION, ok, self._pf_detail(val_bt.metrics), val_bt.metrics
            )
        )
        if not ok:
            return report

        # 3) FORWARD_TEST — rolling out-of-sample walk-forward efficiency.
        wf = self._wf.run(strategy=candidate.name, genome=genome, samples=forward)
        ok = wf.efficiency >= self._min_wf_eff and wf.aggregate_oos.profit_factor >= 1.0
        report.stages.append(
            StageReport(
                ValidationStage.FORWARD_TEST,
                ok,
                f"walk-forward efficiency={wf.efficiency:.2f}",
                wf.aggregate_oos,
            )
        )
        if not ok:
            return report

        # 4) PAPER_REPLAY — full-history replay net of frictions.
        replay = self._bt.run(
            strategy=candidate.name,
            genome=genome,
            samples=list(train) + list(validation) + list(forward),
        )
        ok = replay.metrics.total_return > 0.0 and replay.metrics.max_drawdown <= self._max_dd
        report.stages.append(
            StageReport(
                ValidationStage.PAPER_REPLAY, ok, self._pf_detail(replay.metrics), replay.metrics
            )
        )
        if not ok:
            return report

        # 5) SHADOW — Monte-Carlo robustness stands in for shadow-mode stability.
        trades = evaluate(genome, forward)
        mc = self._mc.run(strategy=candidate.name, trades=trades)
        ok = mc.robustness >= self._min_robustness and mc.prob_profit >= 0.5
        report.stages.append(
            StageReport(
                ValidationStage.SHADOW,
                ok,
                f"robustness={mc.robustness:.2f}, prob_profit={mc.prob_profit:.2f}",
                replay.metrics,
            )
        )
        # PRODUCTION is never auto-entered here — the human-gated Promotion Engine
        # is the only door, and only if SHADOW passed.
        return report

    @staticmethod
    def _pf_detail(metrics: PerformanceMetrics) -> str:
        return (
            f"trades={metrics.trades}, pf={metrics.profit_factor:.2f}, "
            f"dd={metrics.max_drawdown:.2f}, sharpe={metrics.sharpe:.2f}"
        )

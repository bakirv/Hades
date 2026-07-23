"""Experiment Engine — every change becomes a measured, reproducible experiment.

Nothing in Hades is ever "just changed". Adjusting a TP or SL, adding or removing
a feature, swapping a model, tuning a parameter — each is expressed as an
:class:`ExperimentSpec` and run here, against copied history, producing an
:class:`ExperimentResult` with a full metric set and a conclusion. The engine
dispatches a spec to the right sub-engine (backtest / walk-forward / Monte-Carlo /
optimisation / feature-discovery) and never mutates production.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from hades.contexts.research.application.backtest_engine import BacktestingEngine
from hades.contexts.research.application.feature_discovery import FeatureDiscoveryEngine
from hades.contexts.research.application.monte_carlo import MonteCarloEngine
from hades.contexts.research.application.optimizer import ParameterOptimizer
from hades.contexts.research.application.strategies import default_genome, evaluate
from hades.contexts.research.application.walk_forward import WalkForwardEngine
from hades.contexts.research.domain.models import (
    ExperimentKind,
    ExperimentResult,
    ExperimentSpec,
    ExperimentStatus,
    StrategyArchetype,
    StrategyGenome,
)
from hades.contexts.research.domain.ports import HistoricalSample
from hades.shared_kernel.logging import get_logger

_logger = get_logger("research.experiment")


def _genome_from_spec(spec: ExperimentSpec) -> StrategyGenome:
    raw = spec.params.get("archetype", StrategyArchetype.MOMENTUM.value)
    archetype = StrategyArchetype(str(raw))
    genome = default_genome(archetype)
    updates: dict[str, float] = {}
    for key in ("take_profit", "stop_loss", "entry_score", "max_holding_seconds"):
        if key in spec.params:
            updates[key] = float(spec.params[key])
    return genome.model_copy(update=updates) if updates else genome


class ExperimentEngine:
    """Runs an :class:`ExperimentSpec` and returns a reproducible result."""

    def __init__(
        self,
        *,
        backtester: BacktestingEngine | None = None,
        walk_forward: WalkForwardEngine | None = None,
        monte_carlo: MonteCarloEngine | None = None,
        optimizer: ParameterOptimizer | None = None,
        feature_discovery: FeatureDiscoveryEngine | None = None,
    ) -> None:
        self._bt = backtester or BacktestingEngine()
        self._wf = walk_forward or WalkForwardEngine(self._bt)
        self._mc = monte_carlo or MonteCarloEngine()
        self._opt = optimizer or ParameterOptimizer(self._bt)
        self._fd = feature_discovery or FeatureDiscoveryEngine()

    def run(self, spec: ExperimentSpec, samples: Sequence[HistoricalSample]) -> ExperimentResult:
        started = datetime.now(UTC)
        try:
            metrics, conclusion = self._dispatch(spec, samples)
            status = ExperimentStatus.FINISHED
            error: str | None = None
        except Exception as exc:  # a bad experiment must never crash the lab
            _logger.warning("experiment_failed", name=spec.name, error=str(exc))
            metrics, conclusion, status, error = {}, "", ExperimentStatus.FAILED, str(exc)
        return ExperimentResult(
            experiment_id=spec.experiment_id,
            name=spec.name,
            kind=spec.kind,
            status=status,
            metrics=metrics,
            conclusion=conclusion,
            hypothesis=spec.hypothesis,
            started_at=started,
            finished_at=datetime.now(UTC),
            error=error,
        )

    def _dispatch(
        self, spec: ExperimentSpec, samples: Sequence[HistoricalSample]
    ) -> tuple[dict[str, float], str]:
        genome = _genome_from_spec(spec)
        if spec.kind in (ExperimentKind.BACKTEST, ExperimentKind.PARAMETER_CHANGE):
            bt = self._bt.run(strategy=spec.name, genome=genome, samples=samples)
            return self._metric_map(bt.metrics), self._conclude(bt.metrics.total_return)
        if spec.kind is ExperimentKind.WALK_FORWARD:
            wf = self._wf.run(strategy=spec.name, genome=genome, samples=samples)
            metrics = self._metric_map(wf.aggregate_oos)
            metrics["walk_forward_efficiency"] = wf.efficiency
            return metrics, f"OOS efficiency {wf.efficiency:.2f}"
        if spec.kind is ExperimentKind.MONTE_CARLO:
            mc = self._mc.run(strategy=spec.name, trades=evaluate(genome, samples))
            return (
                {
                    "mean_return": mc.mean_return,
                    "p05_return": mc.p05_return,
                    "prob_profit": mc.prob_profit,
                    "robustness": mc.robustness,
                    "worst_drawdown": mc.worst_drawdown,
                },
                f"robustness {mc.robustness:.2f}",
            )
        if spec.kind is ExperimentKind.OPTIMIZATION:
            opt = self._opt.optimize(strategy=spec.name, genome=genome, samples=samples)
            metrics = self._metric_map(opt.best_metrics)
            metrics["best_score"] = opt.best_score
            return metrics, f"best score {opt.best_score:.3f}"
        if spec.kind is ExperimentKind.FEATURE_DISCOVERY:
            proposals = self._fd.analyze(samples)
            return (
                {"proposals": float(len(proposals))},
                f"{len(proposals)} feature proposals",
            )
        # Comparison kinds are handled by the manager (they need multiple genomes).
        r = self._bt.run(strategy=spec.name, genome=genome, samples=samples)
        return self._metric_map(r.metrics), self._conclude(r.metrics.total_return)

    @staticmethod
    def _metric_map(metrics: object) -> dict[str, float]:
        from hades.contexts.research.domain.models import PerformanceMetrics

        assert isinstance(metrics, PerformanceMetrics)
        return {
            "trades": float(metrics.trades),
            "win_rate": metrics.win_rate,
            "total_return": metrics.total_return,
            "expectancy": metrics.expectancy,
            "profit_factor": metrics.profit_factor,
            "sharpe": metrics.sharpe,
            "sortino": metrics.sortino,
            "max_drawdown": metrics.max_drawdown,
            "calmar": metrics.calmar,
        }

    @staticmethod
    def _conclude(total_return: float) -> str:
        if total_return > 0.05:
            return "positive edge net of frictions"
        if total_return > 0.0:
            return "marginal edge — inconclusive"
        return "no edge net of frictions"

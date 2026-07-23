"""Domain events emitted by the Research Lab.

Every meaningful act of the lab is an append-only fact on the bus: an experiment
starting or finishing, a backtest or replay completing, a shadow strategy
updating its virtual ledger, a model or strategy comparison, a proposed feature,
a promotion recommendation being approved or rejected, a report being generated.

Crucially, **none of these is an instruction**. ``StrategyPromoted`` records that
a human approved a promotion; emitting it neither routes an order nor enables
live trading. The Research Lab has no path to the Execution Engine — this
isolation is structural, not merely conventional.
"""

from __future__ import annotations

from pydantic import Field

from hades.contexts.research.domain.models import (
    BacktestResult,
    FeatureProposal,
    ModelComparison,
    MonteCarloResult,
    PerformanceMetrics,
    PromotionDecision,
    ResearchReport,
    StrategyComparison,
    WalkForwardResult,
)
from hades.shared_kernel.domain.events import DomainEvent

# --- experiment lifecycle ----------------------------------------------------


class ExperimentStarted(DomainEvent):
    """An experiment began running (against copied historical data)."""

    aggregate_type: str = "experiment"
    experiment_id: str
    name: str
    kind: str
    hypothesis: str = ""


class ExperimentFinished(DomainEvent):
    """An experiment finished with a reproducible result set."""

    aggregate_type: str = "experiment"
    experiment_id: str
    name: str
    kind: str
    status: str
    metrics: dict[str, float] = Field(default_factory=dict)
    conclusion: str = ""


# Kept for backward compatibility with the phase-1 contract skeleton.
class ExperimentCompleted(DomainEvent):
    """Alias fact: a research experiment finished. Prefer ``ExperimentFinished``."""

    aggregate_type: str = "experiment"
    experiment_id: str
    hypothesis: str
    metrics: dict[str, float]


# --- study completions -------------------------------------------------------


class BacktestCompleted(DomainEvent):
    """A backtest over a historical window finished."""

    aggregate_type: str = "experiment"
    strategy: str
    result: BacktestResult


class WalkForwardCompleted(DomainEvent):
    """A rolling walk-forward validation finished."""

    aggregate_type: str = "experiment"
    strategy: str
    result: WalkForwardResult


class MonteCarloCompleted(DomainEvent):
    """A Monte-Carlo robustness study finished."""

    aggregate_type: str = "experiment"
    strategy: str
    result: MonteCarloResult


class ReplayCompleted(DomainEvent):
    """A historical replay of the analytical pipeline finished."""

    aggregate_type: str = "experiment"
    from_iso: str
    to_iso: str
    events_replayed: int


class ShadowStrategyUpdated(DomainEvent):
    """A shadow strategy updated its virtual ledger (no order, no capital)."""

    aggregate_type: str = "experiment"
    shadow_id: str
    name: str
    metrics: PerformanceMetrics


class ModelCompared(DomainEvent):
    """Production/candidate/shadow models were compared."""

    aggregate_type: str = "model"
    comparison: ModelComparison


class StrategyCompared(DomainEvent):
    """A ranked comparison across strategies was produced."""

    aggregate_type: str = "experiment"
    comparison: StrategyComparison


class FeatureProposed(DomainEvent):
    """The lab proposed a feature change. It never removes a feature itself."""

    aggregate_type: str = "experiment"
    proposal: FeatureProposal


# --- candidates + promotion (recommendation only) ----------------------------


class CandidateProposed(DomainEvent):
    """A validated candidate (feature/signal/strategy) proposed for promotion.

    Emitting this NEVER activates anything. Promotion is a separate human-gated,
    fail-closed step handled outside the lab.
    """

    aggregate_type: str = "experiment"
    candidate_id: str
    kind: str  # "feature" | "signal" | "strategy" | "model"
    summary: str


class StrategyPromoted(DomainEvent):
    """A human approved a candidate's promotion recommendation.

    This records a governance decision; it does not by itself deploy anything to
    production, place an order, or enable live trading.
    """

    aggregate_type: str = "experiment"
    decision: PromotionDecision


class PromotionRejected(DomainEvent):
    """A candidate failed its promotion criteria (or was manually declined)."""

    aggregate_type: str = "experiment"
    decision: PromotionDecision


class ResearchReportGenerated(DomainEvent):
    """A periodic research report was generated and stored."""

    aggregate_type: str = "experiment"
    report: ResearchReport

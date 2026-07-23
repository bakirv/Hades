"""The vocabulary of the Strategy Engine - every value object it reasons with.

Everything here is immutable and *explainable by construction*. A strategy never
reduces a token to a single opaque number: it emits a :class:`StrategySignal`
carrying a :class:`SignalExplanation` (why it fired, which variables moved it,
which conditions favour it and which risks it saw). The :class:`EnsembleBuilder`
fuses those into an :class:`EnsembleSignal` recording *who said what, how much it
weighed and why* - never a simple majority vote.

Nothing in this module decides, sizes or executes a trade. A signal is evidence;
the Risk Manager (a later context in the flow) is the only thing that may act on
the ensemble. The regime enum is deliberately *reused* from the AI Committee
(:class:`~hades.contexts.learning.domain.models.MarketRegime`) so the whole
platform speaks one regime language.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import Field

from hades.contexts.common.domain.value_objects import TokenRef
from hades.contexts.learning.domain.models import MarketRegime
from hades.shared_kernel.domain.base import ValueObject

# --- enums -------------------------------------------------------------------


class SignalType(StrEnum):
    """The only four things a strategy may produce - never an order.

    ``BUY``/``SELL`` express a directional opportunity, ``EXIT`` a reason to
    leave an existing position, ``IGNORE`` an explicit "no opinion" (which still
    carries an explanation of *why* nothing fired).
    """

    BUY = "buy_signal"
    SELL = "sell_signal"
    EXIT = "exit_signal"
    IGNORE = "ignore"

    @property
    def is_actionable(self) -> bool:
        return self is not SignalType.IGNORE

    @property
    def direction(self) -> int:
        """+1 for a long opportunity, -1 for a short/exit, 0 for no opinion."""
        if self is SignalType.BUY:
            return 1
        if self in (SignalType.SELL, SignalType.EXIT):
            return -1
        return 0


class StrategyStatus(StrEnum):
    """Whether a strategy participates in signal generation.

    ``ERROR`` is the *failsafe* state: a strategy that raised is temporarily
    disabled (never removed) so one broken plugin can never stop the others.
    """

    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"


class LifecycleStage(StrEnum):
    """The promotion ladder every new strategy climbs - stages are never skipped.

    A strategy in any stage below :attr:`PRODUCTION` runs in *shadow*: its signals
    are recorded and evaluated but excluded from the production ensemble.
    """

    RESEARCH = "research"
    BACKTEST = "backtest"
    REPLAY = "replay"
    PAPER = "paper"
    SHADOW = "shadow"
    PRODUCTION = "production"


#: The ladder order - used to validate one-step-at-a-time promotions.
LIFECYCLE_ORDER: tuple[LifecycleStage, ...] = (
    LifecycleStage.RESEARCH,
    LifecycleStage.BACKTEST,
    LifecycleStage.REPLAY,
    LifecycleStage.PAPER,
    LifecycleStage.SHADOW,
    LifecycleStage.PRODUCTION,
)


# --- strategy identity / metadata --------------------------------------------


class StrategyMetadata(ValueObject):
    """The full, auditable self-description every strategy must expose.

    Declared once per strategy (its "spec sheet"): what it is, where it trades,
    the regimes it thrives in and the regimes it must never trade, the features it
    consumes, and its historical performance envelope. The dynamic-weighting engine
    reads ``priority``, ``ideal_regimes`` and the historical metrics; the dashboard
    renders the rest.
    """

    name: str
    version: str = "1.0.0"
    description: str = ""
    status: StrategyStatus = StrategyStatus.ENABLED
    priority: int = 100  # lower = evaluated/broken ties earlier; also a weight prior
    supported_markets: tuple[str, ...] = ("solana",)
    ideal_regimes: tuple[MarketRegime, ...] = ()
    forbidden_regimes: tuple[MarketRegime, ...] = ()
    features_used: tuple[str, ...] = ()
    expected_holding_seconds: int = 0
    # Historical performance envelope (priors until live self-evaluation accrues).
    historical_drawdown: float = 0.0  # fraction, e.g. 0.25 == 25%
    historical_sharpe: float = 0.0
    profit_factor: float = 1.0
    win_rate: float = 0.0  # fraction 0..1
    expectancy: float = 0.0  # expected R per trade
    lifecycle_stage: LifecycleStage = LifecycleStage.PRODUCTION

    @property
    def is_production(self) -> bool:
        return self.lifecycle_stage is LifecycleStage.PRODUCTION


# --- market context (strategy input) -----------------------------------------


class MarketContext(ValueObject):
    """Everything a strategy needs about one token - assembled by infrastructure.

    Strategies stay pure: they read this, they never do I/O. It joins the AI
    Committee's fused probabilities and per-facet member scores (0-100) to the
    upstream security / wallet / liquidity / developer facts and the current
    portfolio posture (exposure, risk budget). Every field degrades to a neutral
    default when absent - missing data lowers conviction, it is never an error.

    The member scores are the committee specialists' opinions and the primary
    signal source: ``momentum``, ``liquidity``, ``volatility``, ``wallet``,
    ``security``, ``holder_distribution``, ``developer``, ``behavior``, ``risk``,
    ``timing``, ``microstructure`` - each a legible 0-100.
    """

    token: TokenRef
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    regime: MarketRegime = MarketRegime.UNKNOWN
    regime_confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    # AI Committee fused output.
    ai_prob_roi_positive: float = Field(default=0.5, ge=0.0, le=1.0)
    ai_prob_hit_tp: float = Field(default=0.5, ge=0.0, le=1.0)
    ai_prob_hit_sl: float = Field(default=0.5, ge=0.0, le=1.0)
    ai_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    feature_coverage: float = Field(default=1.0, ge=0.0, le=1.0)

    # Per-facet committee member scores (0..100). Empty => neutral 50 everywhere.
    member_scores: dict[str, float] = Field(default_factory=dict)

    # Upstream facts (best-effort; absence => neutral).
    security_score: float = 50.0
    security_approved: bool = True
    wallet_score: float = 50.0
    developer_score: float = 50.0
    liquidity_usd: float = 0.0
    smart_money_count: int = 0
    dumb_money_count: int = 0
    largest_cluster_pct: float = 0.0
    narrative: str | None = None

    # Portfolio posture (neutral defaults when the read is unavailable).
    exposure_pct: float = 0.0  # current portfolio exposure, % of equity
    risk_budget_remaining_pct: float = 100.0

    # Optional raw/normalised feature bag (from the Feature Store) for strategies
    # that want magnitudes beyond the member scores.
    features: dict[str, float] = Field(default_factory=dict)

    @property
    def ai_expected_edge(self) -> float:
        """P(TP) - P(SL), in [-1, 1] - the committee's directional lean."""
        return round(self.ai_prob_hit_tp - self.ai_prob_hit_sl, 4)

    def member(self, name: str, default: float = 50.0) -> float:
        """A committee member's 0-100 score, or a neutral default when absent."""
        return self.member_scores.get(name, default)

    def feature(self, name: str, default: float = 0.0) -> float:
        return self.features.get(name, default)


class MarketValidation(ValueObject):
    """The verdict of :meth:`Strategy.validate_market` - may this strategy trade?

    ``ok`` false means a *forbidden condition* was met (e.g. the regime is on the
    strategy's blacklist, or security is below its floor); the engine then records
    a ``SignalRejected`` and the strategy produces no actionable signal.
    """

    ok: bool = True
    reason: str = ""


# --- signal explainability ---------------------------------------------------


class SignalExplanation(ValueObject):
    """A fully legible account of a signal - never just a number.

    Answers the four questions the spec demands of every signal: why it appeared
    (``headline`` + ``drivers``), which variables influenced it
    (``influencing_variables``), which conditions favour it (``favorable``) and
    which risks it detected (``risks``).
    """

    headline: str = ""
    drivers: tuple[str, ...] = ()
    influencing_variables: tuple[str, ...] = ()
    favorable: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()


class StrategySignal(ValueObject):
    """One strategy's opinion on one token - evidence, never an order.

    ``internal_score`` is the strategy's own conviction in [0, 1] (independent of
    the ensemble); ``confidence`` is how much to trust that score given coverage
    and agreement. ``shadow`` marks a signal from a non-production strategy: it is
    recorded and evaluated but excluded from the production ensemble.
    """

    strategy: str
    version: str = "1.0.0"
    token: TokenRef
    signal_type: SignalType
    confidence: float = Field(ge=0.0, le=1.0)
    internal_score: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""
    explanation: SignalExplanation = Field(default_factory=SignalExplanation)
    features: dict[str, float] = Field(default_factory=dict)
    regime: MarketRegime = MarketRegime.UNKNOWN
    shadow: bool = False
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_actionable(self) -> bool:
        return self.signal_type.is_actionable


# --- self-evaluation ---------------------------------------------------------


class StrategyOutcome(ValueObject):
    """A realised result attributed back to the strategy that opened the position.

    Fed by the portfolio Position stream (open -> close) so a strategy is judged on
    what it actually earned, not on how loudly it signalled.
    """

    strategy: str
    realized_pnl_usd: float
    holding_seconds: float = 0.0
    win: bool = False
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class StrategyPerformance(ValueObject):
    """The continuously-updated scorecard of one strategy.

    Everything the spec's Self-Evaluation section names. ``degraded`` is a
    derived flag the weighting engine reads to taper (never remove) weight when a
    strategy starts losing its edge.
    """

    strategy: str
    trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    profit_factor: float = 1.0
    sharpe: float = 0.0
    sortino: float = 0.0
    recovery_factor: float = 0.0
    avg_win_usd: float = 0.0
    avg_loss_usd: float = 0.0
    avg_holding_seconds: float = 0.0
    expectancy_usd: float = 0.0
    max_drawdown_usd: float = 0.0
    net_pnl_usd: float = 0.0
    degraded: bool = False
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# --- dynamic weighting -------------------------------------------------------


class StrategyWeight(ValueObject):
    """A strategy's dynamic weight plus the legible decomposition behind it.

    Weight is *never fixed*: it is the product of a base prior (priority) and
    factors for regime fit, recent Sharpe, recent Profit Factor, drawdown,
    consistency, sample size, the AI's confidence and any Research-Lab boost. It
    is floored above zero - a weak strategy is muted, never deleted.
    """

    strategy: str
    weight: float = Field(ge=0.0)
    base: float = 1.0
    regime_factor: float = 1.0
    sharpe_factor: float = 1.0
    profit_factor_factor: float = 1.0
    drawdown_factor: float = 1.0
    consistency_factor: float = 1.0
    sample_factor: float = 1.0
    ai_factor: float = 1.0
    research_factor: float = 1.0
    reason: str = ""


# --- ensemble ----------------------------------------------------------------


class EnsembleContribution(ValueObject):
    """One strategy's signed contribution to the ensemble decision (auditable)."""

    strategy: str
    signal_type: SignalType
    weight: float
    confidence: float
    internal_score: float
    contribution: float  # signed: weight - confidence - score - direction
    shadow: bool = False


class EnsembleSignal(ValueObject):
    """The Strategy Engine's headline output - a weighted fusion, never a vote.

    ``decision`` is the aggregate opinion; ``score`` its net conviction in
    [-1, 1] (positive = buy-side); ``confidence`` the weighted, agreement-adjusted
    trust in it. ``contributions`` records every participating strategy so the
    fusion is fully traceable. It is *information* - the Risk Manager decides.
    """

    token: TokenRef
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    regime: MarketRegime = MarketRegime.UNKNOWN
    decision: SignalType = SignalType.IGNORE
    score: float = 0.0  # net buy-side conviction in [-1, 1]
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    agreement: float = Field(default=0.0, ge=0.0, le=1.0)
    participating: int = 0
    reasoning: str = ""
    contributions: tuple[EnsembleContribution, ...] = ()
    ai_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    correlation_id: str | None = None

    @property
    def is_actionable(self) -> bool:
        return self.decision.is_actionable

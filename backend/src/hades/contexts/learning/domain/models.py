"""The vocabulary of the AI Committee — every value object it reasons with.

Everything here is immutable and *explainable by construction*. The committee
never reduces a token to a single opaque number: every specialist emits a
:class:`Opinion` (a probability, a confidence and the reasons behind both), the
:class:`MetaModel` fuses those into a :class:`MetaPrediction` (three calibrated
probabilities + a confidence), and the whole thing is packaged as a
:class:`CommitteePrediction` that records *who said what and why*.

Nothing in this module decides a trade. A :class:`CommitteePrediction` is
evidence — the Risk Manager (a later context) is the only thing allowed to act
on it. The design mirrors the platform rule stated everywhere else: the AI
*knows and quantifies*; it never buys, sells or sizes.

Design choices that keep it auditable:

* **Transparent models.** Every specialist and the meta-model are *linear-logistic*
  scorers: ``p = sigmoid(bias + Σ wᵢ·xᵢ)`` over named, normalised features. The
  weights are data — stored, versioned and diffable — so a prediction can always
  be decomposed into per-feature contributions. No black boxes.
* **Versioned everything.** Each model is a :class:`ModelCard` with an immutable
  ``(name, version)``; training never overwrites, it appends a new version.
* **Confidence is multi-factor.** It is *not* the model's own output — see
  :class:`ConfidenceFactors`.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from hades.contexts.common.domain.value_objects import TokenRef
from hades.shared_kernel.domain.base import ValueObject

# --- enums -------------------------------------------------------------------


class CommitteeMember(StrEnum):
    """The specialists on the committee — each analyses one facet of the token.

    Every member emits only a quantitative :class:`Opinion`; none decides. The
    meta-model is *not* a member — it is the chair that fuses their opinions.
    """

    LIQUIDITY = "liquidity"
    MOMENTUM = "momentum"
    VOLATILITY = "volatility"
    MARKET_REGIME = "market_regime"
    WALLET = "wallet"
    SECURITY = "security"
    HOLDER_DISTRIBUTION = "holder_distribution"
    DEVELOPER = "developer"
    BEHAVIOR = "behavior"
    RISK = "risk"
    TIMING = "timing"
    MICROSTRUCTURE = "microstructure"


#: Stable identifier of the fusion model in the registry (never a member).
META_MODEL_NAME = "meta"


class MarketRegime(StrEnum):
    """The market state the token is in, as classified by the regime model.

    The regime never sizes a position — it is a *context* the Risk Manager may
    later use to widen/tighten its own thresholds.
    """

    BULL = "bull"
    BEAR = "bear"
    SIDEWAYS = "sideways"
    HIGHLY_VOLATILE = "highly_volatile"
    LOW_LIQUIDITY = "low_liquidity"
    PANIC = "panic"
    FOMO = "fomo"
    UNKNOWN = "unknown"


class ModelStatus(StrEnum):
    """Lifecycle of a model in the registry. Promotion is always human-gated."""

    TRAINED = "trained"  # freshly trained, not yet validated
    VALIDATED = "validated"  # passed validation, eligible for shadow/promotion
    SHADOW = "shadow"  # running alongside prod, decisions ignored
    PROMOTED = "promoted"  # the active model
    REJECTED = "rejected"  # failed validation or lost the comparison
    ARCHIVED = "archived"  # a previously-promoted model, superseded


class DriftKind(StrEnum):
    """The kind of degradation the monitor can detect."""

    NONE = "none"
    DATA = "data"  # input distribution shifted (feature means/vars moved)
    FEATURE = "feature"  # a specific feature's distribution shifted
    CONCEPT = "concept"  # the feature→outcome relationship decayed (live metrics)


class Direction(StrEnum):
    """Whether a contribution pushed the probability up or down."""

    UP = "up"
    DOWN = "down"


# --- features ----------------------------------------------------------------


class NormalizationMethod(StrEnum):
    """How a raw feature is mapped into a model-ready value."""

    IDENTITY = "identity"
    ZSCORE = "zscore"  # (x - mean) / std, then clipped
    MINMAX = "minmax"  # (x - min) / (max - min), clipped to [0, 1]
    CLIP = "clip"  # clip to [min, max] then scale to [0, 1]
    LOG_MINMAX = "log_minmax"  # log1p then min-max (for heavy-tailed magnitudes)
    BOOL = "bool"  # 0/1 passthrough


class FeatureSpec(ValueObject):
    """The full, auditable definition of one model feature.

    This is the Feature Store contract: models are *never* fed raw PostgreSQL
    columns — they consume features that are normalised, versioned, documented
    and traceable to an origin. ``used_by`` records which committee members
    depend on the feature so feature-importance can prune safely.
    """

    name: str  # the namespaced key, e.g. "basic.liquidity"
    description: str
    version: int = 1
    unit: str = "ratio"
    origin: str = "feature_engine"  # which context produced the raw value
    created_at: datetime | None = None
    used_by: tuple[str, ...] = ()  # committee member values
    method: NormalizationMethod = NormalizationMethod.ZSCORE
    # Normalisation parameters (interpretation depends on ``method``).
    center: float = 0.0
    scale: float = 1.0
    lo: float = 0.0
    hi: float = 1.0
    clip_sigma: float = 3.0


class NormalizedVector(ValueObject):
    """A token's features after Feature-Store normalisation — model input.

    ``values`` are the model-ready numbers; ``raw`` keeps the pre-normalisation
    values so explanations can quote human-readable magnitudes. ``coverage`` is
    the fraction of expected features that were actually present (missing inputs
    become a neutral 0.0 and *lower confidence*, never an error).
    """

    token: TokenRef
    at: datetime
    schema_version: int = 1
    values: dict[str, float] = Field(default_factory=dict)
    raw: dict[str, float] = Field(default_factory=dict)
    coverage: float = Field(default=1.0, ge=0.0, le=1.0)
    present: tuple[str, ...] = ()

    def get(self, name: str, default: float = 0.0) -> float:
        return self.values.get(name, default)


# --- opinions (specialist output) --------------------------------------------


class Reason(ValueObject):
    """One legible driver of an opinion: a feature and how much it moved it."""

    feature: str
    text: str
    contribution: float  # signed logit contribution wᵢ·xᵢ
    direction: Direction = Direction.UP


class Opinion(ValueObject):
    """One specialist's quantitative verdict — a probability, never a decision.

    ``probability`` answers only the narrow question that member owns (e.g. the
    Liquidity model's "how healthy is liquidity?"). ``confidence`` says how much
    to trust that probability given feature coverage and how decisive the signal
    was. The reasons make it explainable: a member never returns just a number.
    """

    member: CommitteeMember
    probability: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str = ""
    reasons: tuple[Reason, ...] = ()
    positives: tuple[str, ...] = ()
    negatives: tuple[str, ...] = ()
    features_used: int = 0
    model_version: str = "0"
    abstained: bool = False  # true when coverage was too low to have a view

    @property
    def score(self) -> float:
        """The opinion as a 0-100 score (for dashboards)."""
        return round(self.probability * 100.0, 2)


# --- regime ------------------------------------------------------------------


class RegimeAssessment(ValueObject):
    """The classified market regime plus the full soft distribution behind it."""

    regime: MarketRegime = MarketRegime.UNKNOWN
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    scores: dict[str, float] = Field(default_factory=dict)  # regime -> weight
    detail: str = ""


# --- confidence --------------------------------------------------------------


class ConfidenceFactors(ValueObject):
    """The decomposition of the committee's confidence — never a single number.

    Confidence deliberately depends on *more* than the model output: how good the
    training data was, how many similar historical examples exist, how volatile /
    unusual the current regime is, how complete the feature vector was, and how
    much the specialists agreed. ``final`` is the product-ish fusion the engine
    actually reports; the components are kept so the dashboard can show *why*
    confidence is high or low.
    """

    dataset_quality: float = Field(default=0.5, ge=0.0, le=1.0)
    sample_support: float = Field(default=0.5, ge=0.0, le=1.0)
    coverage: float = Field(default=1.0, ge=0.0, le=1.0)
    agreement: float = Field(default=0.5, ge=0.0, le=1.0)
    regime_stability: float = Field(default=0.5, ge=0.0, le=1.0)
    volatility_penalty: float = Field(default=0.0, ge=0.0, le=1.0)
    final: float = Field(default=0.5, ge=0.0, le=1.0)


# --- meta prediction ---------------------------------------------------------


class MetaPrediction(ValueObject):
    """The chair's fusion of every opinion — three probabilities and a confidence.

    This is the entire quantitative output of the committee. It answers the only
    three questions the Risk Manager needs and it *never* says "buy":

    * ``prob_roi_positive`` — P(the trade would end in profit)
    * ``prob_hit_tp`` — P(price reaches the take-profit before the stop)
    * ``prob_hit_sl`` — P(price reaches the stop-loss first)

    ``member_probabilities`` echoes each specialist's probability so the fusion
    is auditable.
    """

    token: TokenRef
    prob_roi_positive: float = Field(ge=0.0, le=1.0)
    prob_hit_tp: float = Field(ge=0.0, le=1.0)
    prob_hit_sl: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    member_probabilities: dict[str, float] = Field(default_factory=dict)
    model_version: str = "0"

    @property
    def expected_edge(self) -> float:
        """A convenience read: P(TP) - P(SL), in [-1, 1]. Informational only."""
        return round(self.prob_hit_tp - self.prob_hit_sl, 4)


# --- explanation -------------------------------------------------------------


class CommitteeExplanation(ValueObject):
    """A fully legible account of the committee's verdict — never just a %.

    ``drivers`` are the reasons the probability is as high as it is, ``risks`` the
    reasons it is not higher, and ``caveats`` the reasons to distrust the number
    (low coverage, thin data, unstable regime).
    """

    headline: str
    drivers: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    caveats: tuple[str, ...] = ()


# --- the full auditable record -----------------------------------------------


class CommitteePrediction(ValueObject):
    """The complete, self-describing output of one committee run for one token.

    Persisted verbatim so any later decision can be traced back to the exact
    opinions, probabilities, confidence decomposition, regime and model versions
    that informed it. It is *information*; the Risk Manager decides.
    """

    token: TokenRef
    at: datetime
    meta: MetaPrediction
    opinions: tuple[Opinion, ...] = ()
    confidence: ConfidenceFactors = Field(default_factory=ConfidenceFactors)
    regime: RegimeAssessment = Field(default_factory=RegimeAssessment)
    explanation: CommitteeExplanation | None = None
    model_versions: dict[str, str] = Field(default_factory=dict)
    feature_coverage: float = Field(default=1.0, ge=0.0, le=1.0)
    shadow: bool = False  # produced by a shadow model — ignore for decisions
    correlation_id: str | None = None
    duration_ms: float | None = None

    @property
    def prob_roi_positive(self) -> float:
        return self.meta.prob_roi_positive

    @property
    def opinion_of(self) -> dict[str, Opinion]:
        return {o.member.value: o for o in self.opinions}


# --- decision context (what the builder assembles) ---------------------------


class DecisionContext(ValueObject):
    """Everything the committee needs about one token, assembled by infra.

    The engine and its models stay pure: they read this, they never do I/O. It
    joins the normalised feature vector to the upstream security verdict and
    wallet-intelligence snapshot (both optional — absence degrades to neutral,
    never to an error).
    """

    token: TokenRef
    at: datetime
    vector: NormalizedVector
    security_approved: bool = True
    security_score: float = 50.0
    security_sub_scores: dict[str, float] = Field(default_factory=dict)
    # Wallet-intelligence read (from the triggering event's snapshot).
    smart_money_count: int = 0
    dumb_money_count: int = 0
    smart_money_pct_supply: float = 0.0
    avg_wallet_trust: float = 50.0
    avg_wallet_risk: float = 50.0
    cluster_count: int = 0
    largest_cluster_pct: float = 0.0
    wallets_observed: int = 0


# --- model registry ----------------------------------------------------------


class ModelMetrics(ValueObject):
    """The evaluation metrics a model carries in the registry.

    Both classification metrics (the model predicts a probability) and the
    trading metrics its probabilities would have produced on the validation set.
    All optional so a freshly-trained-but-not-yet-backtested model is still
    representable.
    """

    samples: int = 0
    accuracy: float | None = None
    precision: float | None = None
    recall: float | None = None
    auc: float | None = None
    brier: float | None = None
    calibration_error: float | None = None
    log_loss: float | None = None
    # Trading metrics (what its probabilities would have earned).
    roi: float | None = None
    sharpe: float | None = None
    sortino: float | None = None
    profit_factor: float | None = None
    max_drawdown: float | None = None

    def as_dict(self) -> dict[str, float]:
        return {k: v for k, v in self.model_dump().items() if isinstance(v, (int, float))}


class ModelWeights(ValueObject):
    """A transparent linear-logistic model: a bias plus per-feature coefficients.

    This *is* the model — there are no hidden parameters. Inference is
    ``sigmoid(bias + Σ weights[f]·x[f])`` and every term is a legible
    contribution. Serialised as JSON in the registry, so a model is diffable and
    auditable, not an opaque blob.
    """

    bias: float = 0.0
    coefficients: dict[str, float] = Field(default_factory=dict)

    @property
    def feature_names(self) -> tuple[str, ...]:
        return tuple(self.coefficients.keys())


class ModelCard(ValueObject):
    """A registry entry: one immutable, versioned, fully-described model.

    Never overwritten. Every training run appends a new ``(name, version)``. The
    card carries what the spec demands: name, version, date, the dataset it was
    trained on, the features it uses, its metrics, and its lifecycle status.
    """

    model_id: str
    name: str  # a CommitteeMember value or META_MODEL_NAME
    version: str
    kind: str = "logistic"
    created_at: datetime | None = None
    dataset_id: str | None = None
    feature_names: tuple[str, ...] = ()
    weights: ModelWeights = Field(default_factory=ModelWeights)
    # Multi-head models (the meta-model) keep their extra heads here, keyed by
    # head name (``roi_positive`` / ``hit_tp`` / ``hit_sl``). Empty for specialists.
    heads: dict[str, ModelWeights] = Field(default_factory=dict)
    metrics: ModelMetrics = Field(default_factory=ModelMetrics)
    status: ModelStatus = ModelStatus.TRAINED
    trained_on_samples: int = 0
    notes: str = ""
    promoted_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        return self.status is ModelStatus.PROMOTED


# --- datasets & training -----------------------------------------------------


class TrainingSample(ValueObject):
    """One labelled example: the features at decision time joined to the outcome.

    Crucially includes *rejected* opportunities (``was_executed=False``) so the
    committee learns from what it declined as well as what it took — the spec's
    "do not learn only from executed trades / only from gains" rule.
    """

    token_mint: str
    at: datetime
    features: dict[str, float] = Field(default_factory=dict)
    # Labels the models are trained to predict.
    label_roi_positive: bool = False
    label_hit_tp: bool = False
    label_hit_sl: bool = False
    realized_roi: float = 0.0
    was_executed: bool = True
    was_rejected: bool = False
    weight: float = 1.0


class Dataset(ValueObject):
    """An assembled, versioned training set — the Dataset Builder's product."""

    dataset_id: str
    name: str
    created_at: datetime | None = None
    samples: tuple[TrainingSample, ...] = ()
    feature_names: tuple[str, ...] = ()
    from_iso: str | None = None
    to_iso: str | None = None

    @property
    def size(self) -> int:
        return len(self.samples)

    @property
    def positive_rate(self) -> float:
        if not self.samples:
            return 0.0
        return sum(1 for s in self.samples if s.label_roi_positive) / len(self.samples)

    @property
    def executed_count(self) -> int:
        return sum(1 for s in self.samples if s.was_executed)

    @property
    def rejected_count(self) -> int:
        return sum(1 for s in self.samples if s.was_rejected)


# --- validation --------------------------------------------------------------


class FoldResult(ValueObject):
    """One validation fold's out-of-sample metrics."""

    name: str
    train_size: int
    test_size: int
    metrics: ModelMetrics


class ValidationReport(ValueObject):
    """The verdict on whether a candidate model may be deployed.

    A candidate is only eligible for shadow/promotion when it *passes* — it must
    clear absolute quality gates and beat the incumbent out-of-sample. A worse
    model is never deployed (the spec's hard rule). Promotion itself still
    requires a human/policy step; this only says the model is *allowed* to be
    considered.
    """

    model_id: str
    passed: bool
    folds: tuple[FoldResult, ...] = ()
    oos_metrics: ModelMetrics = Field(default_factory=ModelMetrics)
    incumbent_metrics: ModelMetrics | None = None
    improvement: dict[str, float] = Field(default_factory=dict)
    reasons: tuple[str, ...] = ()


# --- monitoring & feature importance -----------------------------------------


class DriftReport(ValueObject):
    """The monitor's read on whether a model has started to degrade."""

    model_id: str
    kind: DriftKind = DriftKind.NONE
    severity: float = Field(default=0.0, ge=0.0, le=1.0)
    triggered: bool = False
    detail: str = ""
    feature_drifts: dict[str, float] = Field(default_factory=dict)
    live_metrics: ModelMetrics | None = None


class FeatureImportance(ValueObject):
    """Which features actually earn their keep — computed continuously.

    ``importances`` is each feature's share of the total absolute contribution.
    The classification lists let the platform prune complexity automatically:
    ``useless`` (near-zero weight), ``redundant`` (highly correlated with a kept
    feature) and ``stale`` (no longer present in recent vectors).
    """

    model_id: str
    computed_at: datetime | None = None
    importances: dict[str, float] = Field(default_factory=dict)
    useless: tuple[str, ...] = ()
    redundant: tuple[str, ...] = ()
    stale: tuple[str, ...] = ()

    @property
    def ranked(self) -> tuple[tuple[str, float], ...]:
        return tuple(sorted(self.importances.items(), key=lambda kv: kv[1], reverse=True))

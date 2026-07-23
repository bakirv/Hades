"""Domain events emitted by the AI Committee (the Learning context).

Every meaningful act of the brain is a fact on the bus: an inference finishing, a
confidence being computed, the committee reaching a verdict, a model being
trained / validated / rejected / promoted, or a drift being detected. They are
append-only and carry enough payload for the dashboard and the audit trail —
never a trade instruction. The Risk Manager (a later context) is the only thing
allowed to react to a :class:`CommitteePredictionGenerated` with an action.
"""

from __future__ import annotations

from hades.contexts.common.domain.value_objects import TokenRef
from hades.contexts.learning.domain.models import (
    CommitteePrediction,
    DriftReport,
    MetaPrediction,
    ValidationReport,
)
from hades.shared_kernel.domain.events import DomainEvent

# --- inference-time events ---------------------------------------------------


class InferenceCompleted(DomainEvent):
    """One committee member finished evaluating a token (a single opinion)."""

    aggregate_type: str = "token"
    token: TokenRef
    member: str
    probability: float
    confidence: float
    model_version: str = "0"


class ConfidenceCalculated(DomainEvent):
    """The multi-factor confidence for a token's committee run was computed."""

    aggregate_type: str = "token"
    token: TokenRef
    confidence: float
    coverage: float
    agreement: float


class CommitteeFinished(DomainEvent):
    """Every member has voted for a token; the meta-model may now fuse them."""

    aggregate_type: str = "token"
    token: TokenRef
    members: int
    abstained: int


class PredictionGenerated(DomainEvent):
    """The meta-model produced the three fused probabilities for a token."""

    aggregate_type: str = "token"
    token: TokenRef
    prediction: MetaPrediction


class CommitteePredictionGenerated(DomainEvent):
    """The complete, auditable committee verdict for a token is ready.

    This is the brain's headline output and the only event a decision-maker
    should consume. It carries probabilities and a full explanation — never a
    buy/sell/size instruction.
    """

    aggregate_type: str = "token"
    token: TokenRef
    prediction: CommitteePrediction


# --- model-lifecycle events --------------------------------------------------


class ModelTrained(DomainEvent):
    """A new candidate model finished training + out-of-sample evaluation."""

    aggregate_type: str = "model"
    model_id: str
    name: str
    model_version: str
    trained_on_samples: int
    metrics: dict[str, float]  # auc, brier, calibration error, etc.


class ModelValidated(DomainEvent):
    """A candidate model passed validation and is eligible for shadow/promotion."""

    aggregate_type: str = "model"
    model_id: str
    report: ValidationReport


class ModelRejected(DomainEvent):
    """A candidate model failed validation or lost to the incumbent — not deployed."""

    aggregate_type: str = "model"
    model_id: str
    reasons: tuple[str, ...] = ()


class ModelPromotionProposed(DomainEvent):
    """The engine proposes replacing the active model. Requires human approval."""

    aggregate_type: str = "model"
    candidate_model_id: str
    incumbent_model_id: str | None = None
    improvement: dict[str, float]


class ModelPromoted(DomainEvent):
    """A model was made active (human/policy approved). The prior is archived."""

    aggregate_type: str = "model"
    model_id: str
    name: str
    model_version: str
    superseded_model_id: str | None = None


class ModelDriftDetected(DomainEvent):
    """The monitor detected a model degrading (data / feature / concept drift)."""

    aggregate_type: str = "model"
    model_id: str
    report: DriftReport

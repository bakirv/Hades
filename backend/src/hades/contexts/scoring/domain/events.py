"""Domain events emitted by the Scoring Engine."""

from __future__ import annotations

from hades.contexts.scoring.domain.models import ScoreResult
from hades.shared_kernel.domain.events import DomainEvent


class FinalScoreComputed(DomainEvent):
    """The composite, probabilistic score for a token is ready for risk review.

    This is the last event before a decision is made. It carries probabilities
    and confidences only — the Risk Manager turns them into an action or a pass.
    """

    aggregate_type: str = "token"
    result: ScoreResult

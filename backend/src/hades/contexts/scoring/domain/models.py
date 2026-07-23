"""Scoring value objects. The engine speaks probabilities, not verdicts."""

from __future__ import annotations

from pydantic import Field

from hades.contexts.common.domain.value_objects import (
    Confidence,
    Probability,
    Score,
    TokenRef,
)
from hades.shared_kernel.domain.base import ValueObject


class ProbabilisticForecast(ValueObject):
    """One calibrated probability with its confidence and a human question.

    ``question`` documents exactly what the probability refers to, so the number
    is never ambiguous (e.g. "ROI > 20% within 60m").
    """

    question: str
    probability: Probability
    confidence: Confidence


class SignalContribution(ValueObject):
    """How much one upstream signal contributed to the composite score."""

    name: str  # "security", "wallet", "liquidity_trend", ...
    contribution: float  # signed weight of this signal
    value: float


class ScoreResult(ValueObject):
    """Full scoring output for a token — probabilities + composite + why.

    This is a recommendation surface, not an order. The Risk Manager consumes it.
    """

    token: TokenRef
    final_score: Score
    forecasts: list[ProbabilisticForecast] = Field(default_factory=list)
    contributions: list[SignalContribution] = Field(default_factory=list)
    model_id: str  # registry id + version of the model that produced this

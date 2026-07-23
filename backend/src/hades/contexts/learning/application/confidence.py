"""Confidence Engine — how much to trust a committee verdict, and why.

Confidence is deliberately *not* the model's own probability. The spec is
explicit that it must depend on many things: the quality of the training data,
how many similar historical examples exist, the current volatility and market
regime, statistical dispersion among the specialists, and how complete the input
was. This engine computes each of those factors and fuses them, returning the
whole :class:`ConfidenceFactors` decomposition so the dashboard can show *why*
confidence is high or low — never a bare number.
"""

from __future__ import annotations

from collections.abc import Sequence

from hades.contexts.learning.application.mathx import clamp, stddev
from hades.contexts.learning.domain.models import (
    ConfidenceFactors,
    Opinion,
    RegimeAssessment,
)


class ConfidenceEngine:
    """Fuses the many drivers of confidence into an explainable decomposition."""

    def compute(
        self,
        *,
        opinions: Sequence[Opinion],
        regime: RegimeAssessment,
        coverage: float,
        volatility: float,
        dataset_quality: float,
        sample_support: float,
    ) -> ConfidenceFactors:
        agreement = self._agreement(opinions)
        volatility_penalty = clamp(volatility)
        regime_stability = clamp(regime.confidence)

        final = self._fuse(
            dataset_quality=dataset_quality,
            sample_support=sample_support,
            coverage=coverage,
            agreement=agreement,
            regime_stability=regime_stability,
            volatility_penalty=volatility_penalty,
        )
        return ConfidenceFactors(
            dataset_quality=round(clamp(dataset_quality), 4),
            sample_support=round(clamp(sample_support), 4),
            coverage=round(clamp(coverage), 4),
            agreement=round(agreement, 4),
            regime_stability=round(regime_stability, 4),
            volatility_penalty=round(volatility_penalty, 4),
            final=round(final, 4),
        )

    @staticmethod
    def _agreement(opinions: Sequence[Opinion]) -> float:
        """1 - dispersion of the active specialists' probabilities."""
        active = [o.probability for o in opinions if not o.abstained]
        if len(active) < 2:
            return 0.4  # cannot corroborate with fewer than two views
        # Max std for values in [0,1] is 0.5; scale dispersion into [0,1].
        dispersion = clamp(stddev(active) / 0.5)
        return clamp(1.0 - dispersion)

    @staticmethod
    def _fuse(
        *,
        dataset_quality: float,
        sample_support: float,
        coverage: float,
        agreement: float,
        regime_stability: float,
        volatility_penalty: float,
    ) -> float:
        base = (
            0.22 * clamp(dataset_quality)
            + 0.18 * clamp(sample_support)
            + 0.24 * clamp(coverage)
            + 0.22 * clamp(agreement)
            + 0.14 * clamp(regime_stability)
        )
        # Volatility erodes confidence multiplicatively (up to -40%).
        return clamp(base * (1.0 - 0.4 * volatility_penalty))

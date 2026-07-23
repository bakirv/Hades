"""Wallet Scoring — many sub-scores into one final, banded Wallet Score.

The scorer blends the reputation and intelligence components into a single 0-100
Wallet Score and assigns a coarse :class:`ReputationBand`. Risk is inverted (high
risk drags the score down); a confirmed scammer is floored regardless of anything
else — safety is not something a wallet can buy back with volume.

Pure and deterministic, and never a black box: it exposes the exact weights, and
:mod:`explainability` turns the same inputs into human reasons.
"""

from __future__ import annotations

from dataclasses import dataclass

from hades.contexts.common.domain.value_objects import Score
from hades.contexts.intelligence.domain.models import (
    MoneyClass,
    ReputationBand,
    WalletScoreBreakdown,
)

#: Weight of each component in the final blend. Trust, smart-money and low risk
#: dominate; experience and consistency support; behaviour is neutral evidence.
DEFAULT_WEIGHTS: dict[str, float] = {
    "trust": 1.6,
    "risk": 1.6,  # applied to (100 - risk)
    "smart_money": 1.5,
    "consistency": 1.0,
    "influence": 0.8,
    "experience": 1.0,
    "behavior": 0.4,
    "profitability": 1.2,
}


@dataclass(frozen=True)
class ScoreResult:
    score: Score
    band: ReputationBand


class WalletScorer:
    """Aggregates the component sub-scores into a final banded Wallet Score."""

    def __init__(
        self,
        *,
        weights: dict[str, float] | None = None,
        smart_band: float = 75.0,
        trusted_band: float = 62.0,
        risky_band: float = 40.0,
        dumb_band: float = 28.0,
    ) -> None:
        self._weights = weights or dict(DEFAULT_WEIGHTS)
        self._smart = smart_band
        self._trusted = trusted_band
        self._risky = risky_band
        self._dumb = dumb_band

    def score(
        self, breakdown: WalletScoreBreakdown, *, money_class: MoneyClass, is_scammer: bool
    ) -> ScoreResult:
        if is_scammer:
            return ScoreResult(score=Score(value=2.0), band=ReputationBand.SCAMMER)

        contributions = {
            "trust": breakdown.trust,
            "risk": 100.0 - breakdown.risk,
            "smart_money": breakdown.smart_money,
            "consistency": breakdown.consistency,
            "influence": breakdown.influence,
            "experience": breakdown.experience,
            "behavior": breakdown.behavior,
            "profitability": breakdown.profitability,
        }
        total_weight = sum(self._weights.values())
        value = sum(self._weights[k] * v for k, v in contributions.items()) / total_weight
        value = max(0.0, min(100.0, value))
        return ScoreResult(score=Score(value=round(value, 2)), band=self._band(value, money_class))

    def _band(self, value: float, money_class: MoneyClass) -> ReputationBand:
        if money_class is MoneyClass.SMART and value >= self._smart:
            return ReputationBand.SMART_MONEY
        if value >= self._trusted:
            return ReputationBand.TRUSTED
        if money_class is MoneyClass.DUMB and value <= self._dumb:
            return ReputationBand.DUMB_MONEY
        if value < self._risky:
            return ReputationBand.RISKY
        return ReputationBand.NEUTRAL

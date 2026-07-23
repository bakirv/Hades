"""Smart / Dumb Money Engine — measure a wallet's predictive value.

Smart money is *earned by evidence*, never assumed. A wallet that repeatedly buys
early, avoids rugs, participates in survivors and shows consistent profitability
accumulates a high smart-money score; one that consistently buys late, holds
through rugs and loses drifts toward dumb money. Both are useful signal.

Requires a minimum amount of resolved history before it will call a wallet either
way — with too little evidence it stays neutral. Pure and deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass

from hades.contexts.common.domain.value_objects import Score
from hades.contexts.intelligence.domain.models import MoneyClass, ReputationScores


@dataclass(frozen=True)
class MoneyEvidence:
    """Resolved-history aggregates that separate smart from dumb money."""

    rugs_participated: int
    successes: int
    tokens_traded: int
    is_known_scammer: bool


@dataclass(frozen=True)
class MoneyVerdict:
    score: Score
    money_class: MoneyClass


class SmartMoneyEngine:
    """Scores predictive value and classifies smart vs dumb money."""

    def __init__(
        self,
        *,
        min_resolved: int = 3,
        smart_threshold: float = 68.0,
        dumb_threshold: float = 35.0,
    ) -> None:
        self._min_resolved = min_resolved
        self._smart = smart_threshold
        self._dumb = dumb_threshold

    def evaluate(self, reputation: ReputationScores, evidence: MoneyEvidence) -> MoneyVerdict:
        if evidence.is_known_scammer:
            return MoneyVerdict(score=Score(value=5.0), money_class=MoneyClass.DUMB)

        # The score blends reputation dimensions that correlate with edge:
        # profitability and consistency carry it, experience and trust support it.
        value = (
            0.40 * reputation.profitability
            + 0.25 * reputation.consistency
            + 0.20 * reputation.experience
            + 0.15 * reputation.trust
        )
        resolved = evidence.rugs_participated + evidence.successes
        if resolved < self._min_resolved:
            # Not enough resolved history to make a call — pull toward neutral.
            value = 0.5 * value + 0.5 * 50.0
            return MoneyVerdict(score=Score(value=round(value, 2)), money_class=MoneyClass.NEUTRAL)

        rug_rate = evidence.rugs_participated / resolved
        value = max(0.0, min(100.0, value - 40.0 * rug_rate))

        if value >= self._smart:
            money_class = MoneyClass.SMART
        elif value <= self._dumb:
            money_class = MoneyClass.DUMB
        else:
            money_class = MoneyClass.NEUTRAL
        return MoneyVerdict(score=Score(value=round(value, 2)), money_class=money_class)

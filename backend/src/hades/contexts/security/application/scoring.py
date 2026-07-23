"""Security Scoring — many sub-scores into one conservative verdict.

The scorer is deliberately not a black box. It:

1. Collects each analyzer's sub-score and reasons.
2. Derives a composite **rug-pull** sub-score from the rug-relevant analyzers.
3. Combines the sub-scores into a weighted final :class:`Score`.
4. Applies the safety floor: **any** ``CRITICAL`` flag hard-vetoes the token,
   capping the final score and rejecting it regardless of everything else.
5. Applies the doubt rule: when too many analyzers ran blind *and* the score is
   only borderline, it rejects — "when in reasonable doubt, reject."

It never sizes a position or places a trade. It answers one question: *does this
token deserve to keep being analysed?*
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hades.contexts.common.domain.value_objects import Score
from hades.contexts.security.domain.models import (
    AnalyzerReport,
    PositiveSignal,
    RiskFlag,
    SecurityDecision,
)

#: Default weight of each analyzer in the final blend. Safety-critical dimensions
#: (authority, liquidity, honeypot, holders, contract) dominate; softer signals
#: contribute but cannot by themselves carry a token.
DEFAULT_WEIGHTS: dict[str, float] = {
    "contract": 1.4,
    "authority": 1.8,
    "liquidity": 1.8,
    "pool": 1.0,
    "holder": 1.5,
    "honeypot": 1.8,
    "developer": 1.0,
    "wallet_cluster": 1.2,
    "transaction": 0.8,
    "behavior": 0.8,
}

#: Analyzers whose sub-scores compose the derived rug-pull safety score.
_RUG_ANALYZERS = ("authority", "liquidity", "holder", "developer", "wallet_cluster")


@dataclass(frozen=True)
class ScoringResult:
    """The aggregated outcome the engine turns into a ``SecurityAssessment``."""

    decision: SecurityDecision
    final: Score
    sub_scores: dict[str, float]
    flags: tuple[RiskFlag, ...]
    positives: tuple[PositiveSignal, ...]
    vetoed: bool
    reject_reasons: tuple[str, ...] = field(default_factory=tuple)


class SecurityScorer:
    """Aggregates analyzer reports into a final, vetoable security verdict."""

    def __init__(
        self,
        *,
        weights: dict[str, float] | None = None,
        min_security_score: float = 60.0,
        max_insufficient_analyzers: int = 3,
        doubt_buffer: float = 15.0,
    ) -> None:
        self._weights = weights or dict(DEFAULT_WEIGHTS)
        self._min_score = min_security_score
        self._max_insufficient = max_insufficient_analyzers
        self._doubt_buffer = doubt_buffer

    def score(self, reports: list[AnalyzerReport], *, trusted: bool = False) -> ScoringResult:
        sub_scores = {r.name: r.score.value for r in reports}
        sub_scores["rug_pull"] = self._rug_pull_score(reports)

        flags = tuple(f for r in reports for f in r.flags)
        positives = tuple(p for r in reports for p in r.positives)
        critical = tuple(f for f in flags if f.is_critical)

        final_value = self._weighted_final(reports)
        vetoed = bool(critical)
        reject_reasons: list[str] = []

        if vetoed:
            # A critical flag floors the score and rejects outright.
            final_value = min(final_value, 5.0)
            reject_reasons.extend(f.code for f in critical)

        if final_value < self._min_score:
            reject_reasons.append("BELOW_MIN_SECURITY_SCORE")

        # Doubt rule: too many blind analyzers + only a borderline score → reject.
        # A trusted (whitelisted) subject waives *doubt* — but never the critical
        # veto or the hard minimum-score floor above.
        insufficient = sum(1 for r in reports if r.insufficient_data)
        if (
            not trusted
            and insufficient >= self._max_insufficient
            and final_value < self._min_score + self._doubt_buffer
        ):
            reject_reasons.append("INSUFFICIENT_DATA_CONFIDENCE")

        decision = SecurityDecision.APPROVED if not reject_reasons else SecurityDecision.REJECTED
        return ScoringResult(
            decision=decision,
            final=Score(value=round(final_value, 2)),
            sub_scores={k: round(v, 2) for k, v in sub_scores.items()},
            flags=flags,
            positives=positives,
            vetoed=vetoed,
            reject_reasons=tuple(dict.fromkeys(reject_reasons)),  # dedupe, keep order
        )

    def _weighted_final(self, reports: list[AnalyzerReport]) -> float:
        total_weight = 0.0
        acc = 0.0
        for report in reports:
            weight = self._weights.get(report.name, 1.0)
            total_weight += weight
            acc += weight * report.score.value
        if total_weight == 0:
            return 0.0
        return acc / total_weight

    def _rug_pull_score(self, reports: list[AnalyzerReport]) -> float:
        by_name = {r.name: r.score.value for r in reports}
        values = [by_name[name] for name in _RUG_ANALYZERS if name in by_name]
        if not values:
            return 0.0
        # The rug-pull safety score is dragged down by its weakest dimension: a
        # single fatal rug vector should dominate, not be averaged away.
        avg = sum(values) / len(values)
        return min(avg, min(values) * 0.5 + avg * 0.5)

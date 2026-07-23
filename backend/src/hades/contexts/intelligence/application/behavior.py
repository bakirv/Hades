"""Behaviour Engine — classify how a wallet trades.

From the activity Hades can observe (breadth of tokens, launch involvement,
supply footprint, lifetime and cadence) it infers a dominant style: whale,
sniper, high-frequency, holder, retail… Confidence is always explicit and stays
low until enough is observed — an honest "unknown" beats a confident guess.

Pure and deterministic. It describes behaviour; it never trades.
"""

from __future__ import annotations

from dataclasses import dataclass

from hades.contexts.intelligence.domain.models import BehaviorProfile, BehaviorType


@dataclass(frozen=True)
class BehaviorEvidence:
    """The observable aggregates behaviour is inferred from."""

    tokens_traded: int
    launches: int
    observations: int
    age_hours: float
    avg_pct_supply: float
    max_pct_supply: float


class BehaviorEngine:
    """Infers a wallet's dominant :class:`BehaviorType`."""

    def __init__(
        self,
        *,
        whale_pct_supply: float = 5.0,
        high_freq_ops_per_day: float = 20.0,
        holder_min_age_hours: float = 168.0,
    ) -> None:
        self._whale_pct = whale_pct_supply
        self._hf_ops_per_day = high_freq_ops_per_day
        self._holder_age = holder_min_age_hours

    def classify(self, evidence: BehaviorEvidence) -> BehaviorProfile:
        if evidence.observations == 0:
            return BehaviorProfile(behavior=BehaviorType.UNKNOWN, confidence=0.0)

        ops_per_day = evidence.observations / max(evidence.age_hours / 24.0, 1e-3)
        confidence = _confidence(evidence.observations)

        # Whale dominates: a large supply footprint is the strongest single tell.
        if evidence.max_pct_supply >= self._whale_pct:
            return BehaviorProfile(
                behavior=BehaviorType.WHALE,
                confidence=confidence,
                detail=f"Controls up to {evidence.max_pct_supply:.1f}% of a token's supply.",
            )
        # Repeated launch involvement → sniper/launcher archetype.
        if evidence.launches >= 2 and evidence.launches / max(evidence.tokens_traded, 1) > 0.5:
            return BehaviorProfile(
                behavior=BehaviorType.SNIPER,
                confidence=confidence,
                detail=f"Involved at launch of {evidence.launches} tokens.",
            )
        if ops_per_day >= self._hf_ops_per_day:
            return BehaviorProfile(
                behavior=BehaviorType.HIGH_FREQUENCY,
                confidence=confidence,
                detail=f"~{ops_per_day:.0f} observed actions/day.",
            )
        if evidence.age_hours >= self._holder_age and ops_per_day < 1.0:
            return BehaviorProfile(
                behavior=BehaviorType.HOLDER,
                confidence=confidence,
                detail="Long-lived wallet with infrequent activity.",
            )
        if evidence.tokens_traded >= 5:
            return BehaviorProfile(
                behavior=BehaviorType.SWING,
                confidence=confidence * 0.8,
                detail=f"Active across {evidence.tokens_traded} tokens.",
            )
        return BehaviorProfile(
            behavior=BehaviorType.RETAIL,
            confidence=confidence * 0.7,
            detail="Small, infrequent participation.",
        )


def _confidence(observations: int) -> float:
    """More observations → more confidence, saturating below 1.0."""
    return min(0.9, 0.2 + 0.1 * observations)

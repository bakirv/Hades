"""Influence Engine — how much should this wallet's opinion weigh?

Not every wallet counts equally. A single wallet with a long, clean, profitable
history should move a decision more than a hundred fresh wallets. The influence
index converts a wallet's earned reputation and experience into a weight the
(later) AI Committee can use to aggregate wallet signals — a proven wallet
entering a token is worth far more than noise.

Pure and deterministic. It produces a weight, never a trade.
"""

from __future__ import annotations

from hades.contexts.intelligence.domain.models import ReputationScores


class InfluenceEngine:
    """Turns reputation + experience + smart-money value into a 0-100 weight."""

    def compute(
        self,
        reputation: ReputationScores,
        *,
        smart_money_score: float,
        observations: int,
    ) -> float:
        # Core standing: what the wallet has proven about itself.
        standing = (
            0.35 * reputation.experience
            + 0.30 * smart_money_score
            + 0.20 * reputation.trust
            + 0.15 * reputation.consistency
        )
        # High risk erodes influence regardless of standing.
        risk_penalty = 0.5 * max(0.0, reputation.risk - 50.0)
        # A wallet observed only once or twice cannot carry full weight yet.
        evidence_factor = min(1.0, observations / 5.0)
        value = (standing - risk_penalty) * evidence_factor
        return max(0.0, min(100.0, value))

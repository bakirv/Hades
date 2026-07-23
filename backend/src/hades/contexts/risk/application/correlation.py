"""Correlation Engine - detects clustered, non-independent positions.

Three tokens riding the same narrative, launched by the same developer, or held
by the same wallet cluster are not three bets - they are one bet made thrice. If
the shared catalyst turns, they all fall together. This engine counts how many
open positions a candidate is *correlated* with (shares a developer, cluster,
narrative or regime), so the manager can refuse to pile more onto an already
concentrated theme. Pure and deterministic.
"""

from __future__ import annotations

from hades.contexts.risk.domain.models import (
    OpenPositionView,
    PortfolioRiskState,
    RiskCandidate,
)


class CorrelationEngine:
    """Counts positions correlated with a candidate along the shared axes."""

    def __init__(self, max_correlated: int = 3) -> None:
        self._max = max_correlated

    def correlated(
        self, candidate: RiskCandidate, state: PortfolioRiskState
    ) -> tuple[OpenPositionView, ...]:
        """Open positions that share a developer, cluster or narrative with the
        candidate (a stricter, more meaningful link than the same regime)."""
        return tuple(p for p in state.open_positions if self._linked(candidate, p))

    def correlation_count(self, candidate: RiskCandidate, state: PortfolioRiskState) -> int:
        return len(self.correlated(candidate, state))

    def is_overcorrelated(self, candidate: RiskCandidate, state: PortfolioRiskState) -> bool:
        """True when adding the candidate would exceed the correlated-position cap.

        The candidate itself counts, so ``count >= max`` means the *next* one is
        one too many.
        """
        return self.correlation_count(candidate, state) >= self._max

    @staticmethod
    def _linked(candidate: RiskCandidate, position: OpenPositionView) -> bool:
        return (
            (candidate.developer is not None and candidate.developer == position.developer)
            or (candidate.cluster is not None and candidate.cluster == position.cluster)
            or (candidate.narrative is not None and candidate.narrative == position.narrative)
        )

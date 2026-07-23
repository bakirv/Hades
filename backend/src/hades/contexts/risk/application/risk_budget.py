"""Risk Budget Engine - each strategy gets a slice, none monopolises capital.

The book runs several strategies (momentum, scalping, launches, swing...). Left
unchecked, one strategy in a hot streak would crowd out the rest and concentrate
the whole book in its failure mode. Each strategy is therefore given a risk
budget - a percentage of equity it may occupy - and this engine refuses a trade
that would push a strategy past its slice. Pure and deterministic.
"""

from __future__ import annotations

from hades.contexts.risk.domain.models import PortfolioRiskState, RiskBudget


class RiskBudgetEngine:
    """Checks a candidate's strategy against its configured capital budget."""

    def __init__(self, budget: RiskBudget) -> None:
        self._budget = budget

    def used_pct(self, state: PortfolioRiskState, strategy: str) -> float:
        """Percentage of equity the strategy currently occupies."""
        equity = state.capital.equity_usd
        if equity <= 0:
            return 0.0
        used = state.strategy_notional_usd.get(strategy, 0.0)
        if used == 0.0:
            used = sum(p.notional_usd for p in state.open_positions if p.strategy == strategy)
        return round(used / equity * 100.0, 4)

    def would_exceed(
        self, state: PortfolioRiskState, strategy: str, proposed_notional_usd: float
    ) -> tuple[bool, float, float]:
        """Return (exceeds, projected_pct, budget_pct) for the strategy."""
        equity = state.capital.equity_usd
        budget_pct = self._budget.budget_pct(strategy)
        if equity <= 0 or proposed_notional_usd <= 0:
            return False, 0.0, budget_pct
        projected = round(
            self.used_pct(state, strategy) + proposed_notional_usd / equity * 100.0, 4
        )
        return projected > budget_pct, projected, budget_pct

"""Promotion Engine — fail-closed, human-gated recommendation of a candidate.

Nothing the lab produces reaches production without passing through here, and even
a perfect candidate only ever earns a *recommendation*. The engine checks a
configurable bar (trades, Sharpe, drawdown, profit factor, expectancy, paper-
positive, shadow-positive) and, critically, requires an explicit ``manual_approve``
that the lab itself can never set. Absent that human action the decision is
REJECTED — fail-closed by construction.

Even an APPROVED-and-manually-approved decision does not deploy anything, place an
order, or enable live trading. It is a governance record; acting on it happens
outside the Research Lab entirely.
"""

from __future__ import annotations

from hades.contexts.research.domain.models import (
    CandidateKind,
    CandidateStrategy,
    PerformanceMetrics,
    PromotionCriteria,
    PromotionDecision,
    PromotionOutcome,
    ValidationStage,
)


class PromotionEngine:
    """Evaluates a candidate against criteria; approval still needs a human."""

    def __init__(self, criteria: PromotionCriteria | None = None) -> None:
        self._criteria = criteria or PromotionCriteria()

    @property
    def criteria(self) -> PromotionCriteria:
        return self._criteria

    def evaluate(
        self,
        candidate: CandidateStrategy,
        *,
        metrics: PerformanceMetrics | None = None,
        kind: CandidateKind = CandidateKind.STRATEGY,
        paper_positive: bool = False,
        shadow_positive: bool = False,
        stage: ValidationStage = ValidationStage.SHADOW,
        manual_approve: bool = False,
    ) -> PromotionDecision:
        c = self._criteria
        metrics = metrics or candidate.metrics
        passed: list[str] = []
        failed: list[str] = []

        def check(name: str, ok: bool) -> None:
            (passed if ok else failed).append(name)

        check(f"min_trades>={c.min_trades}", metrics.trades >= c.min_trades)
        check(f"min_sharpe>={c.min_sharpe}", metrics.sharpe >= c.min_sharpe)
        check(f"max_drawdown<={c.max_drawdown}", metrics.max_drawdown <= c.max_drawdown)
        check(
            f"min_profit_factor>={c.min_profit_factor}",
            metrics.profit_factor >= c.min_profit_factor,
        )
        check(f"min_expectancy>={c.min_expectancy}", metrics.expectancy >= c.min_expectancy)
        if c.require_paper_positive:
            check("paper_positive", paper_positive)
        if c.require_shadow_positive:
            check("shadow_positive", shadow_positive)
        if c.require_manual_approval:
            # The lab can never satisfy this itself — fail-closed.
            check("manual_approval", manual_approve)

        # Reaching production also requires having climbed to the SHADOW gate.
        reached_shadow = stage in (ValidationStage.SHADOW, ValidationStage.PRODUCTION)
        check("reached_shadow_stage", reached_shadow)

        outcome = PromotionOutcome.APPROVED if not failed else PromotionOutcome.REJECTED
        rationale = (
            "all criteria met — recommended for human-approved promotion"
            if outcome is PromotionOutcome.APPROVED
            else f"blocked by: {', '.join(failed)}"
        )
        return PromotionDecision(
            candidate_id=candidate.candidate_id,
            candidate_name=candidate.name,
            kind=kind,
            outcome=outcome,
            stage=stage,
            passed=tuple(passed),
            failed=tuple(failed),
            metrics=metrics,
            rationale=rationale,
            manual_approved=manual_approve,
        )

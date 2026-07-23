"""MarketContextBuilder - turns a committee verdict into a strategy input.

The AI Committee already distilled the upstream analysis into per-facet member
opinions and three fused probabilities. The builder reads those directly - no I/O
of its own - and joins any extra facts from an optional
:class:`~hades.contexts.strategy.domain.ports.StrategyFactsPort` (raw liquidity,
smart/dumb wallet counts, developer address, narrative, portfolio exposure, a
feature bag). Everything degrades to a neutral default when a signal is absent:
missing data lowers conviction downstream, it is never an error.
"""

from __future__ import annotations

from typing import Any

from hades.contexts.learning.domain.events import CommitteePredictionGenerated
from hades.contexts.learning.domain.models import CommitteePrediction
from hades.contexts.strategy.domain.models import MarketContext
from hades.contexts.strategy.domain.ports import StrategyFactsPort


class NullStrategyFactsPort:
    """A facts port that knows nothing - the builder then uses opinions only."""

    async def facts_for(self, mint: str) -> dict[str, Any]:
        return {}


class MarketContextBuilder:
    """Assembles a :class:`MarketContext` from a committee prediction event."""

    def __init__(self, facts: StrategyFactsPort | None = None) -> None:
        self._facts = facts or NullStrategyFactsPort()

    async def build(self, event: CommitteePredictionGenerated) -> MarketContext:
        return await self.from_prediction(
            event.prediction, correlation_ref=_as_opt_str(event.correlation_id)
        )

    async def from_prediction(
        self, prediction: CommitteePrediction, *, correlation_ref: str | None = None
    ) -> MarketContext:
        facts = await self._safe_facts(str(prediction.token.mint))
        member_scores = {op.member.value: op.score for op in prediction.opinions}

        def member(name: str, default: float) -> float:
            return member_scores.get(name, default)

        return MarketContext(
            token=prediction.token,
            at=prediction.at,
            regime=prediction.regime.regime,
            regime_confidence=prediction.regime.confidence,
            ai_prob_roi_positive=prediction.meta.prob_roi_positive,
            ai_prob_hit_tp=prediction.meta.prob_hit_tp,
            ai_prob_hit_sl=prediction.meta.prob_hit_sl,
            ai_confidence=prediction.confidence.final,
            feature_coverage=prediction.feature_coverage,
            member_scores=member_scores,
            security_score=_as_float(facts.get("security_score"), member("security", 50.0)),
            security_approved=_as_bool(facts.get("security_approved"), default=True),
            wallet_score=_as_float(facts.get("wallet_score"), member("wallet", 50.0)),
            developer_score=_as_float(facts.get("developer_score"), member("developer", 50.0)),
            liquidity_usd=_as_float(facts.get("liquidity_usd"), 0.0),
            smart_money_count=_as_int(facts.get("smart_money_count"), 0),
            dumb_money_count=_as_int(facts.get("dumb_money_count"), 0),
            largest_cluster_pct=_as_float(facts.get("largest_cluster_pct"), 0.0),
            narrative=_as_opt_str(facts.get("narrative")),
            exposure_pct=_as_float(facts.get("exposure_pct"), 0.0),
            risk_budget_remaining_pct=_as_float(facts.get("risk_budget_remaining_pct"), 100.0),
            features=_as_feature_map(facts.get("features")),
        )

    async def _safe_facts(self, mint: str) -> dict[str, Any]:
        try:
            return dict(await self._facts.facts_for(mint))
        except Exception:  # facts are optional - never fail the build on them
            return {}


def _as_float(value: object, default: float) -> float:
    return float(value) if isinstance(value, (int, float)) else default


def _as_int(value: object, default: int) -> int:
    return int(value) if isinstance(value, (int, float)) else default


def _as_bool(value: object, *, default: bool) -> bool:
    return bool(value) if isinstance(value, bool) else default


def _as_opt_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _as_feature_map(value: object) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, float] = {}
    for key, raw in value.items():
        if isinstance(key, str) and isinstance(raw, (int, float)):
            out[key] = float(raw)
    return out

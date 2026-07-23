"""BaseStrategy - the shared machinery behind every strategy plugin.

A concrete strategy is intentionally tiny: it declares its :class:`StrategyMetadata`
(``_describe``) and implements one pure method, :meth:`_evaluate`, that turns a
:class:`MarketContext` into an :class:`Evaluation` (a decision + a conviction +
the legible drivers/risks). :class:`BaseStrategy` supplies everything else the
:class:`~hades.contexts.strategy.domain.ports.Strategy` interface requires:
validation, confidence, reasoning, signal assembly and lifecycle hooks.

This keeps the 15 plugins focused on *market logic* and guarantees they all speak
the same interface, are all explainable, and are all pure (no I/O). The base can
never touch the database or the Execution Engine - it holds no such collaborator.
"""

from __future__ import annotations

import contextlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from hades.contexts.strategy.domain.models import (
    LifecycleStage,
    MarketContext,
    MarketValidation,
    SignalExplanation,
    SignalType,
    StrategyMetadata,
    StrategySignal,
    StrategyStatus,
)


@dataclass
class Evaluation:
    """A strategy's raw read of a token, before it is dressed into a signal.

    ``score`` is the conviction *magnitude* in [0, 1]; the sign is carried by
    ``signal_type``. The string lists become the signal's explanation.
    """

    signal_type: SignalType
    score: float = 0.0
    headline: str = ""
    drivers: tuple[str, ...] = ()
    influencing: tuple[str, ...] = ()
    favorable: tuple[str, ...] = ()
    risks: tuple[str, ...] = field(default_factory=tuple)


def unit(score_0_100: float) -> float:
    """Map a 0-100 committee score into [0, 1], clamped."""
    return max(0.0, min(1.0, score_0_100 / 100.0))


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


class BaseStrategy(ABC):
    """Base class implementing the whole Strategy interface bar market logic."""

    def __init__(self) -> None:
        self._metadata: StrategyMetadata = self._describe()
        self._params: dict[str, Any] = {}

    # -- what subclasses provide ---------------------------------------------

    @classmethod
    @abstractmethod
    def _describe(cls) -> StrategyMetadata:
        """Return the strategy's immutable self-description."""

    @abstractmethod
    def _evaluate(self, context: MarketContext) -> Evaluation:
        """The strategy's market logic - pure, no I/O."""

    # -- interface -----------------------------------------------------------

    @property
    def metadata(self) -> StrategyMetadata:
        return self._metadata

    @property
    def name(self) -> str:
        return self._metadata.name

    async def initialize(self) -> None:
        """Default: nothing to set up. Override for warm-up work."""
        return None

    def load_configuration(self, params: dict[str, Any]) -> None:
        """Apply operator config. Recognised keys override metadata in place.

        Recognised: ``enabled`` (bool -> status), ``priority`` (int),
        ``lifecycle_stage`` (str), plus any strategy-specific parameters which are
        stored on ``self._params`` for :meth:`_evaluate` to read (e.g. thresholds
        and a ``sensitivity`` multiplier).
        """
        self._params = dict(params)
        updates: dict[str, Any] = {}
        if "enabled" in params:
            updates["status"] = (
                StrategyStatus.ENABLED if bool(params["enabled"]) else StrategyStatus.DISABLED
            )
        if "priority" in params:
            updates["priority"] = int(params["priority"])
        if "lifecycle_stage" in params:
            with contextlib.suppress(ValueError):
                updates["lifecycle_stage"] = LifecycleStage(str(params["lifecycle_stage"]))
        if updates:
            self._metadata = self._metadata.model_copy(update=updates)

    def validate_market(self, context: MarketContext) -> MarketValidation:
        """Reject when a forbidden condition holds. Subclasses may extend."""
        meta = self._metadata
        if context.regime in meta.forbidden_regimes:
            return MarketValidation(ok=False, reason=f"regime {context.regime.value} is forbidden")
        if not context.security_approved:
            return MarketValidation(ok=False, reason="security not approved")
        min_security = float(self._params.get("min_security_score", 0.0))
        if context.security_score < min_security:
            return MarketValidation(
                ok=False,
                reason=f"security {context.security_score:.0f} < floor {min_security:.0f}",
            )
        min_liquidity = float(self._params.get("min_liquidity_usd", 0.0))
        if min_liquidity > 0.0 and 0.0 < context.liquidity_usd < min_liquidity:
            return MarketValidation(
                ok=False,
                reason=f"liquidity ${context.liquidity_usd:.0f} < floor ${min_liquidity:.0f}",
            )
        return MarketValidation(ok=True)

    def generate_signal(self, context: MarketContext) -> StrategySignal:
        """Assemble the full, explainable signal (validation-guarded)."""
        validation = self.validate_market(context)
        if not validation.ok:
            return self._signal(
                context,
                Evaluation(
                    signal_type=SignalType.IGNORE,
                    score=0.0,
                    headline="market validation failed",
                    risks=(validation.reason,),
                ),
            )
        return self._signal(context, self._evaluate(context))

    def calculate_confidence(self, context: MarketContext) -> float:
        return self._confidence(context, self._evaluate(context))

    def calculate_reasoning(self, context: MarketContext) -> SignalExplanation:
        return self._explanation(self._evaluate(context))

    async def shutdown(self) -> None:
        return None

    def override_metadata(self, **updates: Any) -> None:
        """Replace metadata fields in place (status, lifecycle_stage, weight prior)."""
        self._metadata = self._metadata.model_copy(update=updates)

    # -- shared helpers ------------------------------------------------------

    @property
    def sensitivity(self) -> float:
        """Operator dial (default 1.0): >1 makes the strategy quicker to fire."""
        try:
            return max(0.1, min(3.0, float(self._params.get("sensitivity", 1.0))))
        except (TypeError, ValueError):
            return 1.0

    def _confidence(self, context: MarketContext, ev: Evaluation) -> float:
        """Trust in the assessment: conviction x AI agreement x coverage."""
        if ev.signal_type is SignalType.IGNORE:
            # An abstention is still "confident" in proportion to coverage.
            return round(clamp01(0.4 * context.feature_coverage + 0.2), 4)
        raw = 0.45 * ev.score + 0.35 * context.ai_confidence + 0.20 * context.feature_coverage
        return round(clamp01(raw), 4)

    def _explanation(self, ev: Evaluation) -> SignalExplanation:
        return SignalExplanation(
            headline=ev.headline or f"{self.name}: {ev.signal_type.value}",
            drivers=ev.drivers,
            influencing_variables=ev.influencing,
            favorable=ev.favorable,
            risks=ev.risks,
        )

    def _signal(self, context: MarketContext, ev: Evaluation) -> StrategySignal:
        confidence = self._confidence(context, ev)
        explanation = self._explanation(ev)
        reasoning = explanation.headline
        if ev.drivers:
            reasoning = f"{reasoning} - {'; '.join(ev.drivers)}"
        return StrategySignal(
            strategy=self.name,
            version=self._metadata.version,
            token=context.token,
            signal_type=ev.signal_type,
            confidence=confidence,
            internal_score=round(clamp01(ev.score), 4),
            reasoning=reasoning,
            explanation=explanation,
            features=dict(context.member_scores),
            regime=context.regime,
            shadow=not self._metadata.is_production,
        )

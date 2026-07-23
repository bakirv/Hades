"""Domain events emitted by the Strategy Engine.

Every meaningful act is a fact on the bus: a strategy loading or being disabled,
a signal generated or rejected, a weight being updated, a strategy erroring (and
being temporarily muted by the failsafe), a shadow strategy activating, or a
strategy being promoted a rung up the lifecycle ladder. The headline is
:class:`EnsembleSignalGenerated` - the fused, weighted opinion the Risk Manager
may consume. None of these is a trade instruction; strategies only detect.
"""

from __future__ import annotations

from hades.contexts.common.domain.value_objects import TokenRef
from hades.contexts.strategy.domain.models import (
    EnsembleSignal,
    LifecycleStage,
    StrategySignal,
)
from hades.shared_kernel.domain.events import DomainEvent

# --- lifecycle events --------------------------------------------------------


class StrategyLoaded(DomainEvent):
    """A strategy plugin was registered and initialised."""

    aggregate_type: str = "strategy"
    strategy: str
    strategy_version: str
    lifecycle_stage: str
    priority: int = 100


class StrategyDisabled(DomainEvent):
    """A strategy was disabled (by config or by the failsafe)."""

    aggregate_type: str = "strategy"
    strategy: str
    reason: str = ""


class StrategyError(DomainEvent):
    """A strategy raised while evaluating a token; it was muted, not removed.

    The engine continues with the other strategies - one broken plugin never
    stops Hades.
    """

    aggregate_type: str = "strategy"
    strategy: str
    error: str


class ShadowActivated(DomainEvent):
    """A strategy began running in shadow (recorded + evaluated, not ensembled)."""

    aggregate_type: str = "strategy"
    strategy: str
    lifecycle_stage: str


class StrategyPromoted(DomainEvent):
    """A strategy advanced exactly one rung up the lifecycle ladder."""

    aggregate_type: str = "strategy"
    strategy: str
    previous_stage: str
    new_stage: str
    reason: str = ""

    @staticmethod
    def stage(value: LifecycleStage) -> str:
        return value.value


# --- signal events -----------------------------------------------------------


class SignalGenerated(DomainEvent):
    """One strategy produced an actionable signal for a token."""

    aggregate_type: str = "token"
    token: TokenRef
    signal: StrategySignal


class SignalRejected(DomainEvent):
    """A strategy declined to signal on a token (forbidden condition / no edge)."""

    aggregate_type: str = "token"
    token: TokenRef
    strategy: str
    reason: str = ""


class WeightUpdated(DomainEvent):
    """A strategy's dynamic weight changed materially after re-evaluation."""

    aggregate_type: str = "strategy"
    strategy: str
    weight: float
    previous_weight: float
    reason: str = ""


class EnsembleSignalGenerated(DomainEvent):
    """The fused, weighted opinion of every production strategy for a token.

    This is the Strategy Engine's headline output and the only event a decision
    maker (the Risk Manager) should consume. It carries the full contribution
    breakdown and an explanation - never a buy/sell/size instruction.
    """

    aggregate_type: str = "token"
    token: TokenRef
    ensemble: EnsembleSignal

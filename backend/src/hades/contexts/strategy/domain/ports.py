"""Ports defined by the Strategy Engine.

The most important is :class:`Strategy`: the single interface every plugin
implements, so the engine can host dozens of strategies without knowing any of
their internals. The rest are persistence seams (signals, performance) and an
optional facts port used by infrastructure to enrich the :class:`MarketContext`.

A strategy depends on *nothing* concrete: it receives a pure
:class:`~hades.contexts.strategy.domain.models.MarketContext` and returns value
objects. It never reaches the database and never calls the Execution Engine -
those couplings are structurally impossible because the interface exposes no such
collaborators.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from hades.contexts.strategy.domain.models import (
    MarketContext,
    MarketValidation,
    SignalExplanation,
    StrategyMetadata,
    StrategyOutcome,
    StrategyPerformance,
    StrategySignal,
)


@runtime_checkable
class Strategy(Protocol):
    """THE single interface every strategy plugin implements.

    The lifecycle mirrors the spec exactly: ``initialize`` -> ``load_configuration``
    -> (per token) ``validate_market`` -> ``generate_signal`` (which internally uses
    ``calculate_confidence`` + ``calculate_reasoning``) -> ``shutdown``. A strategy
    is pure and side-effect-free: it must never access the database or the
    Execution Engine.
    """

    @property
    def metadata(self) -> StrategyMetadata:
        """The strategy's immutable self-description (name, regimes, metrics...)."""
        ...

    async def initialize(self) -> None:
        """One-time setup before the strategy sees any token."""
        ...

    def load_configuration(self, params: dict[str, Any]) -> None:
        """Apply operator-supplied parameters (sensitivity, thresholds, toggles)."""
        ...

    def validate_market(self, context: MarketContext) -> MarketValidation:
        """Reject up front when a *forbidden condition* holds (never trade it)."""
        ...

    def generate_signal(self, context: MarketContext) -> StrategySignal:
        """Produce a BUY/SELL/EXIT/IGNORE signal with confidence + explanation."""
        ...

    def calculate_confidence(self, context: MarketContext) -> float:
        """How much to trust this signal, in [0, 1] (coverage + decisiveness)."""
        ...

    def calculate_reasoning(self, context: MarketContext) -> SignalExplanation:
        """The legible account of why the signal fired and what risks it saw."""
        ...

    async def shutdown(self) -> None:
        """Release any resources; the strategy will not be called again."""
        ...


@runtime_checkable
class SignalStore(Protocol):
    """Durable, best-effort persistence of the signal + ensemble trail."""

    async def save_signal(self, snapshot: dict[str, Any]) -> None: ...

    async def save_ensemble(self, snapshot: dict[str, Any]) -> None: ...

    async def recent_signals(self, *, limit: int = 50) -> list[dict[str, Any]]: ...

    async def recent_ensembles(self, *, limit: int = 50) -> list[dict[str, Any]]: ...


@runtime_checkable
class PerformanceStore(Protocol):
    """Holds each strategy's self-evaluation scorecard and raw outcomes."""

    async def record_outcome(self, outcome: StrategyOutcome) -> None: ...

    async def performance(self, strategy: str) -> StrategyPerformance | None: ...

    async def all_performance(self) -> dict[str, StrategyPerformance]: ...


@runtime_checkable
class StrategyFactsPort(Protocol):
    """Optional enrichment for the :class:`MarketContext` (liquidity, features...).

    Everything degrades to a neutral default when the port knows nothing, so the
    engine never fails because a fact is missing.
    """

    async def facts_for(self, mint: str) -> dict[str, Any]: ...

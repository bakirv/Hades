"""Integration tests for the Strategy Engine orchestration.

Exercises the whole flow through the real engine: event emission, the failsafe
(one strategy raising never stops the others), shadow exclusion from the
production ensemble, and the self-evaluation loop fed off the Position stream.
"""

from __future__ import annotations

from decimal import Decimal

from hades.contexts.common.domain.value_objects import Money, TokenMint, TokenRef
from hades.contexts.learning.domain.models import MarketRegime
from hades.contexts.portfolio.domain.events import PositionClosed, PositionOpened
from hades.contexts.strategy.application.base import BaseStrategy, Evaluation
from hades.contexts.strategy.application.factory import build_strategy_engine
from hades.contexts.strategy.application.subscriber import StrategyHandler
from hades.contexts.strategy.domain.events import (
    EnsembleSignalGenerated,
    ShadowActivated,
    SignalGenerated,
    StrategyError,
    StrategyLoaded,
)
from hades.contexts.strategy.domain.models import (
    LifecycleStage,
    MarketContext,
    SignalType,
    StrategyMetadata,
)
from hades.contexts.strategy.infrastructure.stores import (
    InMemoryPerformanceStore,
    InMemorySignalStore,
)
from hades.shared_kernel.config import get_settings
from hades.shared_kernel.domain.events import DomainEvent
from hades.shared_kernel.domain.identifiers import new_id
from hades.shared_kernel.events import InMemoryEventBus

_TOKEN = TokenRef(mint=TokenMint(address="M" * 44), symbol="MEME")


class _AlwaysBuy(BaseStrategy):
    @classmethod
    def _describe(cls) -> StrategyMetadata:
        return StrategyMetadata(name="always_buy", ideal_regimes=(MarketRegime.BULL,))

    def _evaluate(self, context: MarketContext) -> Evaluation:
        return Evaluation(
            signal_type=SignalType.BUY, score=0.9, headline="always buy", drivers=("test",)
        )


class _Boom(BaseStrategy):
    @classmethod
    def _describe(cls) -> StrategyMetadata:
        return StrategyMetadata(name="boom")

    def _evaluate(self, context: MarketContext) -> Evaluation:
        raise RuntimeError("boom")


class _ShadowExit(BaseStrategy):
    @classmethod
    def _describe(cls) -> StrategyMetadata:
        return StrategyMetadata(name="shadow_exit", lifecycle_stage=LifecycleStage.SHADOW)

    def _evaluate(self, context: MarketContext) -> Evaluation:
        return Evaluation(signal_type=SignalType.EXIT, score=0.9, headline="shadow exit")


def _capture(bus: InMemoryEventBus, name: str) -> list[DomainEvent]:
    events: list[DomainEvent] = []

    async def handler(event: DomainEvent) -> None:
        events.append(event)

    bus.subscribe(name, handler)
    return events


def _ctx() -> MarketContext:
    return MarketContext(token=_TOKEN, regime=MarketRegime.BULL, ai_confidence=0.7)


def _build() -> tuple[object, InMemoryEventBus, InMemoryPerformanceStore, InMemorySignalStore]:
    bus = InMemoryEventBus()
    perf = InMemoryPerformanceStore()
    signals = InMemorySignalStore()
    bundle = build_strategy_engine(
        get_settings(),
        event_bus=bus,
        performance_store=perf,
        signal_store=signals,
        strategies=[_AlwaysBuy(), _Boom(), _ShadowExit()],
    )
    return bundle, bus, perf, signals


async def test_initialize_announces_strategies_and_shadows() -> None:
    bundle, bus, _perf, _sig = _build()
    loaded = _capture(bus, StrategyLoaded.__name__)
    shadowed = _capture(bus, ShadowActivated.__name__)

    await bundle.engine.initialize()  # type: ignore[attr-defined]

    assert {e.strategy for e in loaded if isinstance(e, StrategyLoaded)} == {
        "always_buy",
        "boom",
        "shadow_exit",
    }
    assert [e.strategy for e in shadowed if isinstance(e, ShadowActivated)] == ["shadow_exit"]


async def test_failsafe_isolates_a_broken_strategy() -> None:
    bundle, bus, _perf, _sig = _build()
    errors = _capture(bus, StrategyError.__name__)
    generated = _capture(bus, SignalGenerated.__name__)
    ensembles = _capture(bus, EnsembleSignalGenerated.__name__)

    ensemble = await bundle.engine.evaluate(_ctx())  # type: ignore[attr-defined]

    # The broken strategy raised, was caught and reported…
    assert any(isinstance(e, StrategyError) and e.strategy == "boom" for e in errors)
    # …the healthy one still produced its BUY…
    assert any(
        isinstance(e, SignalGenerated) and e.signal.strategy == "always_buy" for e in generated
    )
    # …and a fused ensemble was still emitted.
    assert len(ensembles) == 1
    assert ensemble.decision is SignalType.BUY


async def test_shadow_strategy_is_recorded_but_not_in_the_decision() -> None:
    bundle, _bus, _perf, _sig = _build()
    ensemble = await bundle.engine.evaluate(_ctx())  # type: ignore[attr-defined]
    # Only the production BUY drives the decision; the shadow EXIT is excluded.
    assert ensemble.decision is SignalType.BUY
    assert ensemble.participating == 1
    assert any(c.shadow for c in ensemble.contributions)


async def test_repeated_errors_mute_the_strategy() -> None:
    bundle, _bus, _perf, _sig = _build()
    registry = bundle.registry  # type: ignore[attr-defined]
    for _ in range(get_settings().strategy.error_threshold):
        await bundle.engine.evaluate(_ctx())  # type: ignore[attr-defined]
    assert "boom" not in {s.name for s in registry.active()}  # failsafe muted it
    assert "boom" in registry  # but it was never removed


async def test_self_evaluation_attributes_position_outcomes() -> None:
    bundle, bus, perf, _sig = _build()
    handler = StrategyHandler(bundle.engine, bundle.context_builder)  # type: ignore[attr-defined]
    handler.register(bus)

    position_id = str(new_id())
    await bus.publish(
        PositionOpened(
            aggregate_id=position_id,
            token=_TOKEN,
            entry_price=Money(amount=Decimal(1)),
            quantity=Decimal(100),
            notional=Money(amount=Decimal(100)),
            tags={"strategy": "always_buy"},
        )
    )
    await bus.publish(
        PositionClosed(
            aggregate_id=position_id,
            exit_price=Money(amount=Decimal("1.2")),
            realized_pnl=Money(amount=Decimal(20)),
            reason="take_profit",
        )
    )

    scorecard = await perf.performance("always_buy")
    assert scorecard is not None
    assert scorecard.trades == 1
    assert scorecard.wins == 1
    assert scorecard.net_pnl_usd == 20.0

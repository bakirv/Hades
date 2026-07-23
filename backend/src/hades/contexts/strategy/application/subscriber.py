"""Strategy subscriber - runs the engine after the AI Committee.

The Strategy Engine sits between the committee and the Risk Manager:

    committee ─CommitteePredictionGenerated─► [context builder -> strategy engine]
        ─► SignalGenerated / EnsembleSignalGenerated

Reacting to an event is the sanctioned cross-context coupling: the engine never
calls the committee. Shadow *committee* predictions are ignored (they compare
models). The engine emits per-strategy signals and a fused ensemble - it executes
nothing.

It also closes the self-evaluation loop off the Position stream: a strategy is
credited/debited when a position it was attributed to (via the ``strategy`` tag)
opens and later closes, so weight tapering is driven by realised results.
"""

from __future__ import annotations

from hades.contexts.learning.domain.events import CommitteePredictionGenerated
from hades.contexts.portfolio.domain.events import PositionClosed, PositionOpened
from hades.contexts.strategy.application.context_builder import MarketContextBuilder
from hades.contexts.strategy.application.engine import StrategyEngine
from hades.contexts.strategy.domain.models import StrategyOutcome
from hades.shared_kernel.domain.events import DomainEvent
from hades.shared_kernel.events import EventBus
from hades.shared_kernel.logging import get_logger

_logger = get_logger("strategy.subscriber")


class StrategyHandler:
    """Runs the Strategy Engine whenever the committee finishes a token."""

    def __init__(self, engine: StrategyEngine, builder: MarketContextBuilder) -> None:
        self._engine = engine
        self._builder = builder
        # position_id -> (strategy, opened_epoch) for outcome attribution.
        self._open: dict[str, tuple[str, float]] = {}

    def register(self, event_bus: EventBus) -> None:
        event_bus.subscribe(CommitteePredictionGenerated.__name__, self.handle_prediction)
        event_bus.subscribe(PositionOpened.__name__, self.handle_position_opened)
        event_bus.subscribe(PositionClosed.__name__, self.handle_position_closed)

    async def handle_prediction(self, event: DomainEvent) -> None:
        if not isinstance(event, CommitteePredictionGenerated):
            return
        if event.prediction.shadow:
            return  # a shadow committee model never drives strategy evaluation
        try:
            context = await self._builder.build(event)
            await self._engine.evaluate(context)
        except Exception as exc:  # one token must never break the subscriber
            _logger.warning("strategy_skipped", mint=str(event.token.mint), error=str(exc))

    async def handle_position_opened(self, event: DomainEvent) -> None:
        if not isinstance(event, PositionOpened):
            return
        strategy = event.tags.get("strategy")
        if strategy and strategy in self._engine.registry:
            self._open[str(event.aggregate_id)] = (strategy, event.occurred_at.timestamp())

    async def handle_position_closed(self, event: DomainEvent) -> None:
        if not isinstance(event, PositionClosed):
            return
        record = self._open.pop(str(event.aggregate_id), None)
        if record is None:
            return
        strategy, opened_epoch = record
        pnl = float(event.realized_pnl.amount)
        holding = max(0.0, event.occurred_at.timestamp() - opened_epoch)
        await self._engine.record_outcome(
            StrategyOutcome(
                strategy=strategy,
                realized_pnl_usd=pnl,
                holding_seconds=holding,
                win=pnl > 0,
            )
        )

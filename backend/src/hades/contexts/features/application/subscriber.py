"""Feature computation handler — reacts to token discovery.

Subscribing to the Scanner's ``TokenDiscovered`` domain event is the sanctioned
cross-context coupling (react to events, never call in). On each discovery it
assembles the inputs bundle and asks the Feature Engine to compute + store the
vector. This is the "features" stage of the acquisition pipeline, kept decoupled.
"""

from __future__ import annotations

from hades.contexts.features.application.feature_engine import FeatureEngine
from hades.contexts.features.domain.ports import FeatureInputsAssembler
from hades.contexts.scanner.domain.events import TokenDiscovered
from hades.shared_kernel.domain.events import DomainEvent
from hades.shared_kernel.events import EventBus
from hades.shared_kernel.logging import get_logger

_logger = get_logger("features.subscriber")


class FeatureComputationHandler:
    """Computes features whenever a token is discovered."""

    def __init__(self, engine: FeatureEngine, assembler: FeatureInputsAssembler) -> None:
        self._engine = engine
        self._assembler = assembler

    def register(self, event_bus: EventBus) -> None:
        event_bus.subscribe(TokenDiscovered.__name__, self.handle)

    async def handle(self, event: DomainEvent) -> None:
        if not isinstance(event, TokenDiscovered):
            return
        try:
            inputs = await self._assembler.build(
                event.token, hint_liquidity=float(event.initial_liquidity.amount)
            )
            await self._engine.compute(inputs)
        except Exception as exc:  # never let one token break the subscriber
            _logger.warning(
                "feature_computation_failed", mint=str(event.token.mint), error=str(exc)
            )

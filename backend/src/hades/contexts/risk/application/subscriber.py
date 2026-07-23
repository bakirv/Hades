"""Risk subscriber - runs the guardian at the end of the analytical pipeline.

The Risk Manager sits after the AI Committee:

    scanner -> features -> security -> intelligence -> committee -> **risk**

It subscribes to the committee's ``CommitteePredictionGenerated`` - the only
event a decision-maker is allowed to act on - assembles the candidate (the
committee's probabilities joined to the upstream security/wallet/liquidity
facts) and the current portfolio state, and asks the manager for a verdict.

Reacting to an event is the sanctioned cross-context coupling: the Risk Manager
never calls the committee. Shadow predictions are ignored (they exist only to
compare models). Nothing here executes - the manager emits ``TradeApproved`` /
``TradeRejected``; the Execution Engine (later) is what acts.
"""

from __future__ import annotations

from hades.contexts.learning.domain.events import CommitteePredictionGenerated
from hades.contexts.risk.application.manager import RiskManager
from hades.contexts.risk.domain.ports import PortfolioReadPort, RiskContextBuilder
from hades.shared_kernel.domain.events import DomainEvent
from hades.shared_kernel.events import EventBus
from hades.shared_kernel.logging import get_logger

_logger = get_logger("risk.subscriber")


class RiskHandler:
    """Runs the Risk Manager whenever the committee finishes a token."""

    def __init__(
        self,
        manager: RiskManager,
        builder: RiskContextBuilder,
        portfolio: PortfolioReadPort,
    ) -> None:
        self._manager = manager
        self._builder = builder
        self._portfolio = portfolio

    def register(self, event_bus: EventBus) -> None:
        event_bus.subscribe(CommitteePredictionGenerated.__name__, self.handle)

    async def handle(self, event: DomainEvent) -> None:
        if not isinstance(event, CommitteePredictionGenerated):
            return
        if event.prediction.shadow:
            return  # shadow models never drive a decision
        try:
            candidate = await self._builder.build(event)
            state = await self._portfolio.risk_state()
            await self._manager.evaluate(candidate, state)
        except Exception as exc:  # one token must never break the subscriber
            _logger.warning("risk_skipped", mint=str(event.token.mint), error=str(exc))

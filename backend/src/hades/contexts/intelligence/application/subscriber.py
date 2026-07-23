"""Wallet-intelligence handler — reacts to completed security analysis.

Subscribing to the Security Engine's ``SecurityScoreComputed`` event is the
sanctioned cross-context coupling (react to events, never call in). It fires for
every token the platform fully analysed — approved *and* rejected — which is
exactly the population whose wallets we want to learn from. On each event the
assembler gathers the wallet observations (deployer, top holders, their funders)
and hands the batch to the :class:`WalletIntelligenceEngine`.

This is the ``security → intelligence`` stage of the flow, kept decoupled.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from hades.contexts.intelligence.application.engine import WalletIntelligenceEngine
from hades.contexts.intelligence.domain.models import WalletObservationBatch
from hades.contexts.security.domain.events import SecurityScoreComputed
from hades.shared_kernel.domain.events import DomainEvent
from hades.shared_kernel.events import EventBus
from hades.shared_kernel.logging import get_logger

_logger = get_logger("intelligence.subscriber")


@runtime_checkable
class WalletObservationAssembler(Protocol):
    """Builds the wallet-observation batch for a token from a security event.

    The concrete assembler (infrastructure) performs all I/O — top-holder reads,
    funder lookups, known-address sets — so the engine and its analyzers stay
    pure.
    """

    async def build(self, event: SecurityScoreComputed) -> WalletObservationBatch: ...


class WalletIntelligenceHandler:
    """Builds wallet intelligence whenever a token's security analysis completes."""

    def __init__(
        self, engine: WalletIntelligenceEngine, assembler: WalletObservationAssembler
    ) -> None:
        self._engine = engine
        self._assembler = assembler

    def register(self, event_bus: EventBus) -> None:
        event_bus.subscribe(SecurityScoreComputed.__name__, self.handle)

    async def handle(self, event: DomainEvent) -> None:
        if not isinstance(event, SecurityScoreComputed):
            return
        try:
            batch = await self._assembler.build(event)
            await self._engine.process(batch)
        except Exception as exc:  # never let one token break the subscriber
            _logger.warning(
                "intelligence_skipped",
                mint=str(event.token.mint),
                error=str(exc),
            )

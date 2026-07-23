"""End-to-end Wallet Intelligence engine: registry, versioning, clusters, events."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from hades.contexts.common.domain.value_objects import TokenMint, TokenRef, WalletAddress
from hades.contexts.intelligence.application.behavior import BehaviorEngine
from hades.contexts.intelligence.application.clustering import ClusterBuilder
from hades.contexts.intelligence.application.engine import WalletIntelligenceEngine
from hades.contexts.intelligence.application.funding import FundingAnalyzer
from hades.contexts.intelligence.application.influence import InfluenceEngine
from hades.contexts.intelligence.application.metrics import IntelligenceMetrics
from hades.contexts.intelligence.application.profiler import WalletProfiler
from hades.contexts.intelligence.application.reputation import ReputationEngine
from hades.contexts.intelligence.application.scoring import WalletScorer
from hades.contexts.intelligence.application.smart_money import SmartMoneyEngine
from hades.contexts.intelligence.domain.events import (
    ClusterCreated,
    WalletIntelligenceComputed,
    WalletRegistered,
)
from hades.contexts.intelligence.domain.models import (
    WalletObservation,
    WalletObservationBatch,
    WalletRole,
)
from hades.contexts.intelligence.infrastructure.stores import (
    InMemoryClusterStore,
    InMemoryKnowledgeBase,
    InMemoryRelationshipStore,
    InMemoryTimelineStore,
)
from hades.contexts.intelligence.infrastructure.wallet_repository import (
    InMemoryWalletRepository,
)
from hades.shared_kernel.domain.events import DomainEvent
from hades.shared_kernel.events import InMemoryEventBus
from hades.shared_kernel.observability import MetricsRegistry

_DEPLOYER = "D" * 44
_H1 = "H" * 44
_H2 = "G" * 44
_FUNDER = "F" * 44


class _Harness:
    def __init__(self) -> None:
        self.bus = InMemoryEventBus()
        self.repo = InMemoryWalletRepository()
        self.timeline = InMemoryTimelineStore()
        self.relationships = InMemoryRelationshipStore()
        self.clusters = InMemoryClusterStore()
        self.kb = InMemoryKnowledgeBase()
        self.events: list[DomainEvent] = []
        for name in (
            WalletRegistered.__name__,
            ClusterCreated.__name__,
            WalletIntelligenceComputed.__name__,
        ):
            self.bus.subscribe(name, self._collect)
        profiler = WalletProfiler(
            reputation=ReputationEngine(),
            behavior=BehaviorEngine(),
            smart_money=SmartMoneyEngine(),
            influence=InfluenceEngine(),
            scorer=WalletScorer(),
        )
        self.engine = WalletIntelligenceEngine(
            profiler=profiler,
            cluster_builder=ClusterBuilder(min_members=3),
            funding_analyzer=FundingAnalyzer(),
            repository=self.repo,
            timeline=self.timeline,
            relationships=self.relationships,
            clusters=self.clusters,
            knowledge_base=self.kb,
            event_bus=self.bus,
            metrics=IntelligenceMetrics(MetricsRegistry()),
        )

    async def _collect(self, event: DomainEvent) -> None:
        self.events.append(event)

    def count(self, kind: type[DomainEvent]) -> int:
        return sum(1 for e in self.events if isinstance(e, kind))


def _batch(now: datetime) -> WalletObservationBatch:
    token = TokenRef(mint=TokenMint(address="M" * 44))
    obs = (
        WalletObservation(
            address=_DEPLOYER,
            role=WalletRole.DEPLOYER,
            pct_supply=2.0,
            funders=(_FUNDER,),
            dex="raydium",
            at=now,
        ),
        WalletObservation(
            address=_H1, role=WalletRole.HOLDER, pct_supply=9.0, funders=(_FUNDER,), at=now
        ),
        WalletObservation(
            address=_H2, role=WalletRole.HOLDER, pct_supply=7.0, funders=(_FUNDER,), at=now
        ),
    )
    return WalletObservationBatch(token=token, now=now, observations=obs)


@pytest.mark.asyncio
async def test_engine_registers_wallets_and_builds_cluster() -> None:
    h = _Harness()
    now = datetime.now(UTC)
    snapshot = await h.engine.process(_batch(now))

    assert snapshot.wallets_observed == 3
    assert snapshot.new_wallets == 3
    assert await h.repo.count() == 3
    # Three wallets share one funder → exactly one cluster of three.
    assert len(h.clusters.clusters) == 1
    cluster = next(iter(h.clusters.clusters.values()))
    assert cluster.size == 3
    assert snapshot.cluster_count == 1

    assert h.count(WalletRegistered) == 3
    assert h.count(ClusterCreated) == 1
    assert h.count(WalletIntelligenceComputed) == 1
    # Timeline + knowledge base grew, funding edges recorded.
    assert len(h.timeline.entries) == 3
    assert len(h.kb.records) == 3
    assert len(h.relationships.edges) == 3


@pytest.mark.asyncio
async def test_engine_never_deletes_history_and_versions_grow() -> None:
    h = _Harness()
    first = datetime.now(UTC)
    await h.engine.process(_batch(first))
    v1 = await h.repo.get(WalletAddress(address=_H1))
    assert v1 is not None and v1.version == 1

    # Same wallets seen again later → new versions, no new registrations.
    later = first + timedelta(days=2)
    snapshot = await h.engine.process(_batch(later))
    assert snapshot.new_wallets == 0
    v2 = await h.repo.get(WalletAddress(address=_H1))
    assert v2 is not None and v2.version == 2
    assert v2.observations == 2
    # The append-only history retains every version (nothing overwritten away).
    versions = [p.version for p in h.repo.history if str(p.address) == _H1]
    assert versions == [1, 2]
    # Only the three registrations from the first pass ever fired.
    assert h.count(WalletRegistered) == 3


@pytest.mark.asyncio
async def test_engine_isolates_bad_wallet_addresses() -> None:
    h = _Harness()
    now = datetime.now(UTC)
    token = TokenRef(mint=TokenMint(address="M" * 44))
    obs = (
        WalletObservation(address="too-short", role=WalletRole.HOLDER, pct_supply=1.0, at=now),
        WalletObservation(address=_H1, role=WalletRole.HOLDER, pct_supply=5.0, at=now),
    )
    snapshot = await h.engine.process(
        WalletObservationBatch(token=token, now=now, observations=obs)
    )
    # The invalid pubkey is skipped; the valid one is still profiled.
    assert snapshot.wallets_observed == 1
    assert await h.repo.count() == 1

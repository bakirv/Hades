"""Wallet Intelligence Engine — turn observations into permanent knowledge.

Given a pre-assembled :class:`WalletObservationBatch` for one analysed token, the
engine:

    1. Builds coordinated-wallet clusters across the batch.
    2. For every observed wallet: loads its prior profile (or registers a new
       one), folds in the observation (reputation, behaviour, smart-money,
       influence, score), persists the new version, appends to the append-only
       timeline and knowledge base, records funding relationships, and emits the
       granular events.
    3. Persists the clusters and emits ``ClusterCreated``.
    4. Aggregates a per-token :class:`IntelligenceSnapshot` and emits
       ``WalletIntelligenceComputed`` for the (later) AI Committee.

It orchestrates; it never reads the chain itself (the assembler does) and it
never decides a trade, enables live trading, or runs any ML. Persistence is
best-effort and every wallet is isolated — one failure never sinks the batch.
Nothing is ever deleted: profiles gain versions, history only grows.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Iterable

from hades.contexts.common.domain.value_objects import WalletAddress
from hades.contexts.intelligence.application.clustering import ClusterBuilder
from hades.contexts.intelligence.application.funding import FundingAnalyzer
from hades.contexts.intelligence.application.metrics import IntelligenceMetrics
from hades.contexts.intelligence.application.profiler import WalletProfiler
from hades.contexts.intelligence.domain.events import (
    BehaviorChanged,
    ClusterCreated,
    FundingRelationshipFound,
    ReputationUpdated,
    SmartMoneyDetected,
    WalletIntelligenceComputed,
    WalletProfileComputed,
    WalletRegistered,
    WalletScoreUpdated,
    WalletUpdated,
)
from hades.contexts.intelligence.domain.models import (
    Cluster,
    FundingLink,
    IntelligenceSnapshot,
    MoneyClass,
    Relationship,
    TimelineEntry,
    WalletObservation,
    WalletObservationBatch,
    WalletProfile,
    WalletRole,
)
from hades.contexts.intelligence.domain.ports import (
    ClusterStore,
    KnowledgeBase,
    RelationshipStore,
    TimelineStore,
    WalletRepository,
)
from hades.shared_kernel.domain.identifiers import new_id
from hades.shared_kernel.events import EventBus
from hades.shared_kernel.logging import get_logger

_logger = get_logger("intelligence.engine")

_ROLE_TIMELINE_KIND = {
    WalletRole.DEPLOYER: "launch",
    WalletRole.EARLY_BUYER: "early_buy",
    WalletRole.HOLDER: "observed_holder",
    WalletRole.FUNDER: "funded_wallet",
}


class WalletIntelligenceEngine:
    """Composes profiler + clustering + stores into the growing knowledge base."""

    def __init__(
        self,
        *,
        profiler: WalletProfiler,
        cluster_builder: ClusterBuilder,
        funding_analyzer: FundingAnalyzer,
        repository: WalletRepository,
        timeline: TimelineStore,
        relationships: RelationshipStore,
        clusters: ClusterStore,
        knowledge_base: KnowledgeBase,
        event_bus: EventBus,
        metrics: IntelligenceMetrics,
    ) -> None:
        self._profiler = profiler
        self._cluster_builder = cluster_builder
        self._funding = funding_analyzer
        self._repo = repository
        self._timeline = timeline
        self._relationships = relationships
        self._clusters = clusters
        self._kb = knowledge_base
        self._bus = event_bus
        self._metrics = metrics

    async def process(self, batch: WalletObservationBatch) -> IntelligenceSnapshot:
        started = asyncio.get_running_loop().time()
        correlation = new_id()
        try:
            snapshot = await self._run(batch, correlation, started)
        except Exception as exc:  # a batch must never crash the subscriber
            self._metrics.errors.inc()
            _logger.error("intelligence_failed", mint=str(batch.token.mint), error=str(exc))
            raise
        finally:
            self._metrics.analysis_seconds.observe(asyncio.get_running_loop().time() - started)
        return snapshot

    # -- orchestration --------------------------------------------------------

    async def _run(
        self, batch: WalletObservationBatch, correlation: str, started: float
    ) -> IntelligenceSnapshot:
        observations = _dedupe(batch.observations)
        detected = self._cluster_builder.build(batch)
        cluster_by_wallet = {member: cluster for cluster in detected for member in cluster.members}

        profiles: list[WalletProfile] = []
        new_wallets = 0
        for observation in observations:
            outcome = await self._process_wallet(observation, batch, cluster_by_wallet, correlation)
            if outcome is None:
                continue
            profile, was_new = outcome
            profiles.append(profile)
            new_wallets += int(was_new)

        await self._persist_clusters(detected, batch, correlation)

        snapshot = self._build_snapshot(batch, profiles, detected, new_wallets, started)
        await self._bus.publish(
            WalletIntelligenceComputed(
                aggregate_id=new_id(),
                correlation_id=correlation,
                token=batch.token,
                snapshot=snapshot,
            )
        )
        self._meter(snapshot, profiles)
        return snapshot

    async def _process_wallet(
        self,
        observation: WalletObservation,
        batch: WalletObservationBatch,
        cluster_by_wallet: dict[str, Cluster],
        correlation: str,
    ) -> tuple[WalletProfile, bool] | None:
        try:
            address = WalletAddress(address=observation.address)
        except ValueError:
            return None  # not a valid pubkey — skip silently
        try:
            prior = await self._safe_get(address)
            funding = self._funding.classify(observation.funders, batch)
            cluster = cluster_by_wallet.get(observation.address)
            profile = self._profiler.build(
                prior,
                observation,
                funding=funding,
                cluster_id=cluster.cluster_id if cluster else None,
                now=batch.now,
            )
            await self._persist_wallet(profile, observation, funding, batch)
            await self._emit_wallet_events(prior, profile, observation, funding, correlation)
            self._metrics.wallets_seen.inc()
            return profile, prior is None
        except Exception as exc:  # one wallet must not sink the batch
            _logger.warning(
                "wallet_intelligence_skipped", address=observation.address, error=str(exc)
            )
            return None

    # -- persistence (best-effort) --------------------------------------------

    async def _safe_get(self, address: WalletAddress) -> WalletProfile | None:
        try:
            return await self._repo.get(address)
        except Exception as exc:
            _logger.warning("wallet_load_failed", address=str(address), error=str(exc))
            return None

    async def _persist_wallet(
        self,
        profile: WalletProfile,
        observation: WalletObservation,
        funding: tuple[FundingLink, ...],
        batch: WalletObservationBatch,
    ) -> None:
        await self._best_effort(self._repo.save(profile), "wallet_save_failed")
        await self._best_effort(
            self._timeline.append(
                [
                    TimelineEntry(
                        address=observation.address,
                        at=batch.now,
                        kind=_ROLE_TIMELINE_KIND.get(observation.role, "observed"),
                        mint=str(batch.token.mint),
                        detail=(
                            f"role={observation.role.value}, supply={observation.pct_supply:.2f}%"
                        ),
                    )
                ]
            ),
            "timeline_append_failed",
        )
        await self._best_effort(
            self._kb.record(
                address=observation.address,
                kind="profile_computed",
                payload={
                    "mint": str(batch.token.mint),
                    "score": profile.score.value,
                    "band": profile.band.value,
                    "version": profile.version,
                },
                at=batch.now,
            ),
            "kb_record_failed",
        )
        if funding:
            edges = [
                Relationship(
                    source=link.source,
                    target=observation.address,
                    kind="funded",
                    weight=1.0,
                )
                for link in funding
            ]
            await self._best_effort(self._relationships.add(edges), "relationship_add_failed")

    async def _persist_clusters(
        self, clusters: tuple[Cluster, ...], batch: WalletObservationBatch, correlation: str
    ) -> None:
        for cluster in clusters:
            await self._best_effort(self._clusters.save(cluster), "cluster_save_failed")
            self._metrics.clusters.inc()
            await self._bus.publish(
                ClusterCreated(
                    aggregate_id=new_id(),
                    correlation_id=correlation,
                    cluster=cluster,
                    token=batch.token,
                )
            )

    # -- events ---------------------------------------------------------------

    async def _emit_wallet_events(
        self,
        prior: WalletProfile | None,
        profile: WalletProfile,
        observation: WalletObservation,
        funding: tuple[FundingLink, ...],
        correlation: str,
    ) -> None:
        if prior is None:
            self._metrics.wallets_registered.inc()
            await self._bus.publish(
                WalletRegistered(
                    aggregate_id=new_id(),
                    correlation_id=correlation,
                    address=observation.address,
                    first_role=observation.role.value,
                )
            )
        else:
            await self._bus.publish(
                WalletUpdated(
                    aggregate_id=new_id(),
                    correlation_id=correlation,
                    address=observation.address,
                    version=profile.version,
                )
            )
        await self._bus.publish(
            WalletProfileComputed(
                aggregate_id=new_id(),
                correlation_id=correlation,
                address=observation.address,
                profile=profile,
            )
        )
        await self._bus.publish(
            ReputationUpdated(
                aggregate_id=new_id(),
                correlation_id=correlation,
                address=observation.address,
                trust=round(profile.reputation.trust, 2),
                risk=round(profile.reputation.risk, 2),
            )
        )
        if _became_smart(prior, profile):
            self._metrics.smart_money.inc()
            await self._bus.publish(
                SmartMoneyDetected(
                    aggregate_id=new_id(),
                    correlation_id=correlation,
                    address=observation.address,
                    smart_money_score=profile.smart_money_score.value,
                )
            )
        if _behavior_changed(prior, profile):
            await self._bus.publish(
                BehaviorChanged(
                    aggregate_id=new_id(),
                    correlation_id=correlation,
                    address=observation.address,
                    behavior=profile.behavior.behavior.value,
                    confidence=round(profile.behavior.confidence, 3),
                )
            )
        if _score_moved(prior, profile):
            await self._bus.publish(
                WalletScoreUpdated(
                    aggregate_id=new_id(),
                    correlation_id=correlation,
                    address=observation.address,
                    score=profile.score.value,
                    band=profile.band.value,
                )
            )
        for link in funding:
            self._metrics.funding_edges.labels(kind=link.kind.value).inc()
            await self._bus.publish(
                FundingRelationshipFound(
                    aggregate_id=new_id(),
                    correlation_id=correlation,
                    source=link.source,
                    target=observation.address,
                    kind=link.kind.value,
                )
            )

    # -- snapshot + metering --------------------------------------------------

    def _build_snapshot(
        self,
        batch: WalletObservationBatch,
        profiles: list[WalletProfile],
        clusters: tuple[Cluster, ...],
        new_wallets: int,
        started: float,
    ) -> IntelligenceSnapshot:
        smart = [p for p in profiles if p.money_class is MoneyClass.SMART]
        dumb = [p for p in profiles if p.money_class is MoneyClass.DUMB]
        funding_sources = len({link.source for p in profiles for link in p.funding})
        return IntelligenceSnapshot(
            token=batch.token,
            wallets_observed=len(profiles),
            new_wallets=new_wallets,
            smart_money_count=len(smart),
            dumb_money_count=len(dumb),
            smart_money_pct_supply=round(sum(p.avg_pct_supply for p in smart), 4),
            avg_trust=round(_avg(p.reputation.trust for p in profiles), 2),
            avg_risk=round(_avg(p.reputation.risk for p in profiles), 2),
            avg_influence=round(_avg(p.influence for p in profiles), 2),
            clusters=clusters,
            funding_sources=funding_sources,
            analyzed_at=batch.now,
            duration_ms=round((asyncio.get_running_loop().time() - started) * 1000.0, 2),
        )

    def _meter(self, snapshot: IntelligenceSnapshot, profiles: list[WalletProfile]) -> None:
        if profiles:
            self._metrics.wallet_score.set(profiles[-1].score.value)

    async def _best_effort(self, coro: Awaitable[None], message: str) -> None:
        try:
            await coro
        except Exception as exc:
            _logger.warning(message, error=str(exc))


# -- helpers ------------------------------------------------------------------


def _dedupe(observations: tuple[WalletObservation, ...]) -> list[WalletObservation]:
    """One observation per wallet, preferring the most significant role/funding."""
    by_address: dict[str, WalletObservation] = {}
    for obs in observations:
        current = by_address.get(obs.address)
        if current is None:
            by_address[obs.address] = obs
            continue
        by_address[obs.address] = _merge_observations(current, obs)
    return list(by_address.values())


def _merge_observations(a: WalletObservation, b: WalletObservation) -> WalletObservation:
    role = a.role if _role_rank(a.role) >= _role_rank(b.role) else b.role
    funders = tuple(dict.fromkeys((*a.funders, *b.funders)))
    return a.model_copy(
        update={
            "role": role,
            "pct_supply": max(a.pct_supply, b.pct_supply),
            "funders": funders,
            "is_known_scammer": a.is_known_scammer or b.is_known_scammer,
            "dex": a.dex or b.dex,
        }
    )


def _role_rank(role: WalletRole) -> int:
    return {
        WalletRole.DEPLOYER: 3,
        WalletRole.EARLY_BUYER: 2,
        WalletRole.HOLDER: 1,
        WalletRole.FUNDER: 0,
    }[role]


def _became_smart(prior: WalletProfile | None, profile: WalletProfile) -> bool:
    if profile.money_class is not MoneyClass.SMART:
        return False
    return prior is None or prior.money_class is not MoneyClass.SMART


def _behavior_changed(prior: WalletProfile | None, profile: WalletProfile) -> bool:
    if prior is None:
        return profile.behavior.behavior.value != "unknown"
    return prior.behavior.behavior is not profile.behavior.behavior


def _score_moved(prior: WalletProfile | None, profile: WalletProfile) -> bool:
    if prior is None:
        return True
    return abs(prior.score.value - profile.score.value) >= 1.0


def _avg(values: Iterable[float]) -> float:
    items = list(values)
    return sum(items) / len(items) if items else 0.0

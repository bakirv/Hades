"""Timeline, relationship, cluster and knowledge-base stores — Postgres + memory.

Every store here is append-only or upsert-latest; none ever deletes. Together they
are the durable substance of the knowledge base: the per-wallet timeline, the
funding/co-holding graph, the detected clusters, and the immutable event ledger.
Each ships a PostgreSQL adapter for the running system and an in-memory twin for
tests.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hades.contexts.common.domain.value_objects import WalletAddress
from hades.contexts.intelligence.domain.models import (
    Cluster,
    Relationship,
    TimelineEntry,
)
from hades.shared_kernel.persistence.database import Database
from hades.shared_kernel.persistence.models import (
    IntelClusterRecord,
    WalletKnowledgeRecord,
    WalletRelationshipRecord,
    WalletTimelineRecord,
)

# --- timeline ----------------------------------------------------------------


class PostgresTimelineStore:
    """PostgreSQL-backed append-only per-wallet timeline."""

    def __init__(self, database: Database) -> None:
        self._db = database

    async def append(self, entries: list[TimelineEntry]) -> None:
        if not entries:
            return
        async with self._db.session() as session:
            session.add_all(
                WalletTimelineRecord(
                    address=e.address, at=e.at, kind=e.kind, mint=e.mint, detail=e.detail
                )
                for e in entries
            )

    async def load(self, address: WalletAddress, *, limit: int = 100) -> list[TimelineEntry]:
        async with self._db.session() as session:
            rows = (
                await session.scalars(
                    select(WalletTimelineRecord)
                    .where(WalletTimelineRecord.address == str(address))
                    .order_by(desc(WalletTimelineRecord.at))
                    .limit(limit)
                )
            ).all()
        return [
            TimelineEntry(address=r.address, at=r.at, kind=r.kind, mint=r.mint, detail=r.detail)
            for r in rows
        ]


class InMemoryTimelineStore:
    """In-process timeline for tests."""

    def __init__(self) -> None:
        self.entries: list[TimelineEntry] = []

    async def append(self, entries: list[TimelineEntry]) -> None:
        self.entries.extend(entries)

    async def load(self, address: WalletAddress, *, limit: int = 100) -> list[TimelineEntry]:
        matching = [e for e in self.entries if e.address == str(address)]
        matching.sort(key=lambda e: e.at, reverse=True)
        return matching[:limit]


# --- relationships -----------------------------------------------------------


class PostgresRelationshipStore:
    """PostgreSQL-backed wallet relationship graph (edges accumulate weight)."""

    def __init__(self, database: Database) -> None:
        self._db = database

    async def add(self, relationships: list[Relationship]) -> None:
        if not relationships:
            return
        async with self._db.session() as session:
            for rel in relationships:
                stmt = (
                    pg_insert(WalletRelationshipRecord)
                    .values(
                        source=rel.source,
                        target=rel.target,
                        kind=rel.kind,
                        weight=rel.weight,
                        observations=rel.observations,
                    )
                    .on_conflict_do_update(
                        index_elements=[
                            WalletRelationshipRecord.source,
                            WalletRelationshipRecord.target,
                            WalletRelationshipRecord.kind,
                        ],
                        set_={
                            "weight": WalletRelationshipRecord.weight + rel.weight,
                            "observations": WalletRelationshipRecord.observations + 1,
                        },
                    )
                )
                await session.execute(stmt)

    async def neighbors(self, address: WalletAddress, *, limit: int = 100) -> list[Relationship]:
        addr = str(address)
        async with self._db.session() as session:
            rows = (
                await session.scalars(
                    select(WalletRelationshipRecord)
                    .where(
                        (WalletRelationshipRecord.source == addr)
                        | (WalletRelationshipRecord.target == addr)
                    )
                    .order_by(desc(WalletRelationshipRecord.weight))
                    .limit(limit)
                )
            ).all()
        return [
            Relationship(
                source=r.source,
                target=r.target,
                kind=r.kind,
                weight=r.weight,
                observations=r.observations,
            )
            for r in rows
        ]


class InMemoryRelationshipStore:
    """In-process relationship graph for tests."""

    def __init__(self) -> None:
        self.edges: dict[tuple[str, str, str], Relationship] = {}

    async def add(self, relationships: list[Relationship]) -> None:
        for rel in relationships:
            key = (rel.source, rel.target, rel.kind)
            current = self.edges.get(key)
            if current is None:
                self.edges[key] = rel
            else:
                self.edges[key] = current.model_copy(
                    update={
                        "weight": current.weight + rel.weight,
                        "observations": current.observations + 1,
                    }
                )

    async def neighbors(self, address: WalletAddress, *, limit: int = 100) -> list[Relationship]:
        addr = str(address)
        matching = [r for r in self.edges.values() if addr in (r.source, r.target)]
        matching.sort(key=lambda r: r.weight, reverse=True)
        return matching[:limit]


# --- clusters ----------------------------------------------------------------


def _cluster_to_vo(row: IntelClusterRecord) -> Cluster:
    return Cluster(
        cluster_id=row.cluster_id,
        members=tuple(str(m) for m in row.members),
        funder=row.funder,
        reason=row.reason,
        confidence=row.confidence,
        pct_supply=row.pct_supply,
    )


class PostgresClusterStore:
    """PostgreSQL-backed cluster store."""

    def __init__(self, database: Database) -> None:
        self._db = database

    async def save(self, cluster: Cluster) -> None:
        values = {
            "cluster_id": cluster.cluster_id,
            "funder": cluster.funder,
            "member_count": cluster.size,
            "reason": cluster.reason,
            "confidence": cluster.confidence,
            "pct_supply": cluster.pct_supply,
            "members": list(cluster.members),
            "detected_at": datetime.now(UTC),
        }
        async with self._db.session() as session:
            stmt = (
                pg_insert(IntelClusterRecord)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=[IntelClusterRecord.cluster_id],
                    set_={
                        "member_count": cluster.size,
                        "pct_supply": cluster.pct_supply,
                        "confidence": cluster.confidence,
                        "members": list(cluster.members),
                    },
                )
            )
            await session.execute(stmt)

    async def for_wallet(self, address: WalletAddress) -> Cluster | None:
        addr = str(address)
        async with self._db.session() as session:
            rows = (
                await session.scalars(
                    select(IntelClusterRecord).order_by(desc(IntelClusterRecord.detected_at))
                )
            ).all()
        for row in rows:
            if addr in row.members:
                return _cluster_to_vo(row)
        return None

    async def recent(self, *, limit: int = 50) -> list[Cluster]:
        async with self._db.session() as session:
            rows = (
                await session.scalars(
                    select(IntelClusterRecord)
                    .order_by(desc(IntelClusterRecord.detected_at))
                    .limit(limit)
                )
            ).all()
        return [_cluster_to_vo(r) for r in rows]


class InMemoryClusterStore:
    """In-process cluster store for tests."""

    def __init__(self) -> None:
        self.clusters: dict[str, Cluster] = {}

    async def save(self, cluster: Cluster) -> None:
        self.clusters[cluster.cluster_id] = cluster

    async def for_wallet(self, address: WalletAddress) -> Cluster | None:
        addr = str(address)
        for cluster in self.clusters.values():
            if addr in cluster.members:
                return cluster
        return None

    async def recent(self, *, limit: int = 50) -> list[Cluster]:
        return list(self.clusters.values())[:limit]


# --- knowledge base ----------------------------------------------------------


class PostgresKnowledgeBase:
    """PostgreSQL-backed append-only intelligence ledger."""

    def __init__(self, database: Database) -> None:
        self._db = database

    async def record(
        self, *, address: str, kind: str, payload: dict[str, object], at: datetime
    ) -> None:
        async with self._db.session() as session:
            session.add(WalletKnowledgeRecord(address=address, kind=kind, payload=payload, at=at))


class InMemoryKnowledgeBase:
    """In-process knowledge ledger for tests."""

    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    async def record(
        self, *, address: str, kind: str, payload: dict[str, object], at: datetime
    ) -> None:
        self.records.append({"address": address, "kind": kind, "payload": payload, "at": at})

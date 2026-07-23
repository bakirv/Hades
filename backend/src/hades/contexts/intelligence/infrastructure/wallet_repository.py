"""Wallet profile repository — PostgreSQL + in-memory.

Upserts the current profile row and appends the version to ``wallet_history`` so
no past reputation is ever lost. Scores and reputation are stored as columns and
JSONB so the full, explainable record survives and can be queried and replayed.
"""

from __future__ import annotations

from sqlalchemy import desc, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hades.contexts.common.domain.value_objects import Score, WalletAddress
from hades.contexts.intelligence.domain.models import (
    BehaviorProfile,
    BehaviorType,
    FundingLink,
    FundingSourceKind,
    MoneyClass,
    ReputationBand,
    ReputationScores,
    WalletExplanation,
    WalletProfile,
)
from hades.shared_kernel.logging import get_logger
from hades.shared_kernel.persistence.database import Database
from hades.shared_kernel.persistence.models import (
    WalletHistoryRecord,
    WalletProfileRecord,
)

_logger = get_logger("intelligence.repository")


def _to_columns(profile: WalletProfile) -> dict[str, object]:
    return {
        "address": str(profile.address),
        "first_seen_at": profile.first_seen_at,
        "last_active_at": profile.last_active_at,
        "observations": profile.observations,
        "tokens_traded": profile.tokens_traded,
        "launches": profile.launches,
        "rugs_participated": profile.rugs_participated,
        "successes": profile.successes,
        "dexes": list(profile.dexes),
        "roles": list(profile.roles),
        "avg_pct_supply": profile.avg_pct_supply,
        "reputation": profile.reputation.model_dump(mode="json"),
        "behavior": profile.behavior.behavior.value,
        "behavior_confidence": profile.behavior.confidence,
        "money_class": profile.money_class.value,
        "smart_money_score": profile.smart_money_score.value,
        "influence": profile.influence,
        "funding": [link.model_dump(mode="json") for link in profile.funding],
        "cluster_id": profile.cluster_id,
        "score": profile.score.value,
        "band": profile.band.value,
        "explanation": (profile.explanation.model_dump(mode="json") if profile.explanation else {}),
        "version": profile.version,
    }


def _to_vo(row: WalletProfileRecord) -> WalletProfile:
    return WalletProfile(
        address=WalletAddress(address=row.address),
        first_seen_at=row.first_seen_at,
        last_active_at=row.last_active_at,
        observations=row.observations,
        tokens_traded=row.tokens_traded,
        launches=row.launches,
        rugs_participated=row.rugs_participated,
        successes=row.successes,
        dexes=tuple(str(d) for d in row.dexes),
        roles=tuple(str(r) for r in row.roles),
        avg_pct_supply=row.avg_pct_supply,
        reputation=ReputationScores(**row.reputation)
        if row.reputation
        else ReputationScores.initial(),
        behavior=BehaviorProfile(
            behavior=BehaviorType(row.behavior), confidence=row.behavior_confidence
        ),
        money_class=MoneyClass(row.money_class),
        smart_money_score=Score(value=row.smart_money_score),
        influence=row.influence,
        funding=tuple(
            FundingLink(
                source=str(f.get("source", "")),
                kind=FundingSourceKind(f.get("kind", "unknown")),
                note=str(f.get("note", "")),
            )
            for f in row.funding
            if isinstance(f, dict) and f.get("source")
        ),
        cluster_id=row.cluster_id,
        score=Score(value=row.score),
        band=ReputationBand(row.band),
        explanation=WalletExplanation(**row.explanation) if row.explanation else None,
        version=row.version,
    )


class PostgresWalletRepository:
    """PostgreSQL-backed wallet profiles + append-only version history."""

    def __init__(self, database: Database) -> None:
        self._db = database

    async def get(self, address: WalletAddress) -> WalletProfile | None:
        async with self._db.session() as session:
            row = await session.scalar(
                select(WalletProfileRecord).where(WalletProfileRecord.address == str(address))
            )
            return _to_vo(row) if row is not None else None

    async def save(self, profile: WalletProfile) -> None:
        columns = _to_columns(profile)
        async with self._db.session() as session:
            update_cols = {
                k: v for k, v in columns.items() if k not in ("address", "first_seen_at")
            }
            stmt = (
                pg_insert(WalletProfileRecord)
                .values(**columns)
                .on_conflict_do_update(
                    index_elements=[WalletProfileRecord.address], set_=update_cols
                )
            )
            await session.execute(stmt)
            session.add(
                WalletHistoryRecord(
                    address=str(profile.address),
                    version=profile.version,
                    score=profile.score.value,
                    band=profile.band.value,
                    reputation=profile.reputation.model_dump(mode="json"),
                    snapshot=profile.model_dump(mode="json"),
                    recorded_at=profile.last_active_at,
                )
            )

    async def top_by_score(
        self, *, limit: int, smart_money_only: bool = False
    ) -> list[WalletProfile]:
        stmt = select(WalletProfileRecord).order_by(desc(WalletProfileRecord.score)).limit(limit)
        if smart_money_only:
            stmt = stmt.where(WalletProfileRecord.money_class == MoneyClass.SMART.value)
        async with self._db.session() as session:
            rows = (await session.scalars(stmt)).all()
        return [_to_vo(r) for r in rows]

    async def count(self) -> int:
        async with self._db.session() as session:
            total = await session.scalar(select(func.count()).select_from(WalletProfileRecord))
        return int(total or 0)


class InMemoryWalletRepository:
    """In-process wallet profiles for tests; keeps a version history too."""

    def __init__(self) -> None:
        self.profiles: dict[str, WalletProfile] = {}
        self.history: list[WalletProfile] = []

    async def get(self, address: WalletAddress) -> WalletProfile | None:
        return self.profiles.get(str(address))

    async def save(self, profile: WalletProfile) -> None:
        self.profiles[str(profile.address)] = profile
        self.history.append(profile)

    async def top_by_score(
        self, *, limit: int, smart_money_only: bool = False
    ) -> list[WalletProfile]:
        values = list(self.profiles.values())
        if smart_money_only:
            values = [p for p in values if p.money_class is MoneyClass.SMART]
        values.sort(key=lambda p: p.score.value, reverse=True)
        return values[:limit]

    async def count(self) -> int:
        return len(self.profiles)

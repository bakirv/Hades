"""Feature store adapters — PostgreSQL (durable) + Redis cache + in-memory.

The store persists every computed vector so features are never recomputed
unnecessarily and training/serving see the same values. Each feature value is a
row (name, value, version, computed_at) keyed by token; the schema version is
stored with every row so a definition change keeps old vectors readable — we
never break compatibility. Redis caches only the *latest* vector (transient).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hades.contexts.common.domain.value_objects import TokenRef
from hades.contexts.features.domain.models import FeatureSet
from hades.shared_kernel.cache import CacheService, RedisProvider
from hades.shared_kernel.logging import get_logger
from hades.shared_kernel.persistence.database import Database
from hades.shared_kernel.persistence.models import Feature, Token

_logger = get_logger("features.store")


class PostgresFeatureStore:
    """Durable feature store — one row per feature value in ``features``."""

    def __init__(self, database: Database) -> None:
        self._db = database

    async def save(self, features: FeatureSet) -> None:
        async with self._db.session() as session:
            token_id = await self._token_id(session, str(features.token.mint))
            if token_id is None:
                _logger.warning("features_for_unknown_token", mint=str(features.token.mint))
                return
            version = str(features.schema_version)
            session.add_all(
                [
                    Feature(
                        token_id=token_id,
                        name=name,
                        value=value,
                        feature_set_version=version,
                        computed_at=features.computed_at,
                    )
                    for name, value in features.values.items()
                ]
            )

    async def latest(self, token: TokenRef) -> FeatureSet | None:
        async with self._db.session() as session:
            token_id = await self._token_id(session, str(token.mint))
            if token_id is None:
                return None
            newest = await session.execute(
                select(Feature.computed_at)
                .where(Feature.token_id == token_id)
                .order_by(Feature.computed_at.desc())
                .limit(1)
            )
            computed_at = newest.scalar_one_or_none()
            if computed_at is None:
                return None
            rows = await session.execute(
                select(Feature.name, Feature.value, Feature.feature_set_version).where(
                    Feature.token_id == token_id, Feature.computed_at == computed_at
                )
            )
            values: dict[str, float] = {}
            version = 1
            for name, value, ver in rows.all():
                if value is not None:
                    values[name] = value
                if ver is not None:
                    version = int(ver)
            return FeatureSet(
                token=token, computed_at=computed_at, schema_version=version, values=values
            )

    async def _token_id(self, session: AsyncSession, mint: str) -> uuid.UUID | None:
        result = await session.execute(select(Token.id).where(Token.mint == mint))
        return result.scalar_one_or_none()


class CachingFeatureStore:
    """Wraps a durable store, caching the latest vector in Redis (transient)."""

    def __init__(
        self,
        inner: PostgresFeatureStore,
        provider: RedisProvider,
        *,
        ttl_seconds: int = 300,
    ) -> None:
        self._inner = inner
        self._cache = CacheService(provider, namespace="features")
        self._ttl = ttl_seconds

    async def save(self, features: FeatureSet) -> None:
        await self._inner.save(features)
        await self._cache.set(
            str(features.token.mint),
            {
                "computed_at": features.computed_at.isoformat(),
                "schema_version": features.schema_version,
                "values": features.values,
            },
            ttl_seconds=self._ttl,
        )

    async def latest(self, token: TokenRef) -> FeatureSet | None:
        cached = await self._cache.get(str(token.mint))
        if cached is not None:
            return FeatureSet(
                token=token,
                computed_at=datetime.fromisoformat(cached["computed_at"]),
                schema_version=cached["schema_version"],
                values=cached["values"],
            )
        return await self._inner.latest(token)


class InMemoryFeatureStore:
    """In-process feature store for tests / single-process runs."""

    def __init__(self) -> None:
        self._by_mint: dict[str, FeatureSet] = {}

    async def save(self, features: FeatureSet) -> None:
        self._by_mint[str(features.token.mint)] = features

    async def latest(self, token: TokenRef) -> FeatureSet | None:
        return self._by_mint.get(str(token.mint))

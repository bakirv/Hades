"""Snapshot repository — the History Builder's durable store.

Writes one ``token_snapshots`` row per captured moment so any historical state can
be reconstructed later (event sourcing for market/feature state). Postgres is the
system of record; an in-memory adapter backs the tests.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hades.contexts.common.domain.value_objects import TokenRef
from hades.shared_kernel.logging import get_logger
from hades.shared_kernel.persistence.database import Database
from hades.shared_kernel.persistence.models import Token, TokenSnapshot

_logger = get_logger("features.snapshots")


class SnapshotRepository:
    """PostgreSQL-backed snapshot writer."""

    def __init__(self, database: Database) -> None:
        self._db = database

    async def save(
        self,
        token: TokenRef,
        *,
        captured_at: datetime,
        state: dict[str, Any],
        schema_version: int = 1,
    ) -> None:
        async with self._db.session() as session:
            token_id = await self._token_id(session, str(token.mint))
            if token_id is None:
                _logger.warning("snapshot_for_unknown_token", mint=str(token.mint))
                return
            session.add(
                TokenSnapshot(
                    token_id=token_id,
                    captured_at=captured_at,
                    schema_version=schema_version,
                    state=state,
                )
            )

    async def _token_id(self, session: AsyncSession, mint: str) -> uuid.UUID | None:
        result = await session.execute(select(Token.id).where(Token.mint == mint))
        return result.scalar_one_or_none()


class InMemorySnapshotRepository:
    """In-process snapshot store for tests."""

    def __init__(self) -> None:
        self.snapshots: list[dict[str, Any]] = []

    async def save(
        self,
        token: TokenRef,
        *,
        captured_at: datetime,
        state: dict[str, Any],
        schema_version: int = 1,
    ) -> None:
        self.snapshots.append(
            {
                "mint": str(token.mint),
                "captured_at": captured_at,
                "state": state,
                "schema_version": schema_version,
            }
        )

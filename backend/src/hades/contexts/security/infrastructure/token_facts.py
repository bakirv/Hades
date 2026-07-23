"""Stored-facts source — reads what the Scanner already persisted for a token.

The Security Engine re-reads authoritative on-chain state itself, but it reuses
the Scanner's stored metadata for the cheap, slow-moving facts: socials, mutable
flag, first-seen time, the last observed pool, and (when known) the deployer.
This avoids re-fetching what another context already gathered.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select

from hades.contexts.common.domain.value_objects import TokenRef
from hades.contexts.security.domain.ports import StoredTokenFacts
from hades.shared_kernel.persistence.database import Database
from hades.shared_kernel.persistence.models import Token, TokenMetadataRecord, Wallet


class PostgresTokenFactsSource:
    """Reads Scanner-stored token facts from PostgreSQL."""

    def __init__(self, database: Database) -> None:
        self._db = database

    async def load(self, token: TokenRef) -> StoredTokenFacts | None:
        mint = str(token.mint)
        async with self._db.session() as session:
            row = await session.scalar(select(Token).where(Token.mint == mint))
            if row is None:
                return None
            meta = await session.scalar(
                select(TokenMetadataRecord).where(TokenMetadataRecord.token_id == row.id)
            )
            deployer = None
            if row.deployer_wallet_id is not None:
                deployer = await session.scalar(
                    select(Wallet.address).where(Wallet.id == row.deployer_wallet_id)
                )
            pool = _pool_attrs(row.attributes)
            has_socials = bool(
                meta and any((meta.website, meta.twitter, meta.telegram, meta.discord))
            )
            return StoredTokenFacts(
                first_seen_at=row.first_seen_at,
                has_socials=has_socials,
                is_mutable=meta.is_mutable if meta else None,
                deployer=deployer,
                pool_address=pool.get("address"),
                pool_dex=pool.get("dex"),
                pool_liquidity_usd=(
                    Decimal(str(pool["liquidity_usd"]))
                    if pool.get("liquidity_usd") is not None
                    else None
                ),
                lp_mint=pool.get("lp_mint"),
            )


def _pool_attrs(attributes: dict[str, Any]) -> dict[str, Any]:
    pool = attributes.get("last_pool") if isinstance(attributes, dict) else None
    return pool if isinstance(pool, dict) else {}


class InMemoryTokenFactsSource:
    """In-process stored-facts source for tests."""

    def __init__(self, facts: dict[str, StoredTokenFacts] | None = None) -> None:
        self._facts = facts or {}

    async def load(self, token: TokenRef) -> StoredTokenFacts | None:
        return self._facts.get(str(token.mint))

"""Security context assembler — gathers everything the analyzers need.

This is where *all* the Security Engine's I/O happens. Given a ``FeaturesComputed``
event it fetches, concurrently where possible:

* the authoritative mint account (authorities, supply, program, extensions),
* the largest holders (+ an optional exact holder count),
* the Scanner-stored facts (socials, mutable flag, pool, deployer),
* the LP burn/lock coverage for the pool,
* a honeypot buy+sell probe,
* the deployer's accumulated reputation,
* the wallet-cluster funding graph,

and assembles them into an immutable :class:`SecurityInputs`. Every step is
best-effort: a failure degrades that field to ``None`` (doubt) without stopping
the analysis. The engine and analyzers then run as pure functions of the result.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import TypeVar

from hades.contexts.common.domain.value_objects import WalletAddress
from hades.contexts.features.domain.events import FeaturesComputed
from hades.contexts.security.domain.models import (
    LiquidityPool,
    SecurityInputs,
)
from hades.contexts.security.domain.ports import (
    ClusterDetector,
    DeveloperReputationStore,
    OnChainReader,
    StoredTokenFacts,
    SwapSimulator,
    TokenFactsSource,
)
from hades.shared_kernel.logging import get_logger

_logger = get_logger("security.assembler")

_T = TypeVar("_T")


class SecurityContextAssembler:
    """Builds a :class:`SecurityInputs` for a token (all I/O lives here)."""

    def __init__(
        self,
        *,
        reader: OnChainReader,
        facts_source: TokenFactsSource,
        swap_simulator: SwapSimulator,
        developer_store: DeveloperReputationStore,
        cluster_detector: ClusterDetector,
        top_holders: int = 20,
        honeypot_probe_usd: float = 50.0,
        fetch_holder_count: bool = False,
    ) -> None:
        self._reader = reader
        self._facts = facts_source
        self._sim = swap_simulator
        self._dev = developer_store
        self._clusters = cluster_detector
        self._top_holders = top_holders
        self._probe_usd = honeypot_probe_usd
        self._fetch_count = fetch_holder_count

    async def build(self, event: FeaturesComputed) -> SecurityInputs:
        token = event.token
        mint = str(token.mint)
        now = datetime.now(UTC)
        features = dict(event.features.values)

        mint_account, holders, stored, honeypot = await asyncio.gather(
            self._safe(self._reader.get_mint_account(mint), None, "mint_account"),
            self._safe(
                self._reader.get_largest_holders(mint, limit=self._top_holders),
                [],
                "holders",
            ),
            self._safe(self._facts.load(token), None, "stored_facts"),
            self._safe(self._sim.probe(token, amount_usd=self._probe_usd), None, "honeypot"),
        )

        holder_count = None
        if self._fetch_count:
            holder_count = await self._safe(
                self._reader.get_holder_count(mint), None, "holder_count"
            )

        deployer = self._deployer(stored)
        developer = None
        if deployer is not None:
            developer = await self._safe(self._dev.get(deployer), None, "developer")

        cluster = await self._safe(self._clusters.detect(token, holders), None, "cluster")

        pool = await self._build_pool(stored)

        return SecurityInputs(
            token=token,
            now=now,
            mint_account=mint_account,
            holders=tuple(holders),
            holder_count=holder_count,
            pool=pool,
            honeypot=honeypot,
            developer=developer,
            deployer=deployer,
            cluster=cluster,
            features=features,
            age_minutes=self._age_minutes(stored, now),
            has_socials=bool(stored.has_socials) if stored else False,
            is_mutable=stored.is_mutable if stored else None,
        )

    async def _build_pool(self, stored: StoredTokenFacts | None) -> LiquidityPool | None:
        if stored is None or stored.pool_address is None:
            return None
        burned = locked = None
        if stored.lp_mint:
            burned, locked = await self._safe(
                self._reader.get_lp_secure_pct(stored.lp_mint), (None, None), "lp"
            )
        return LiquidityPool(
            address=stored.pool_address,
            dex=stored.pool_dex or "unknown",
            liquidity_usd=stored.pool_liquidity_usd or 0,
            lp_mint=stored.lp_mint,
            lp_burned_pct=burned,
            lp_locked_pct=locked,
        )

    @staticmethod
    def _deployer(stored: StoredTokenFacts | None) -> WalletAddress | None:
        if stored is None or not stored.deployer:
            return None
        try:
            return WalletAddress(address=stored.deployer)
        except Exception:
            return None

    @staticmethod
    def _age_minutes(stored: StoredTokenFacts | None, now: datetime) -> float | None:
        if stored is None or stored.first_seen_at is None:
            return None
        seen = stored.first_seen_at
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=UTC)
        return max(0.0, (now - seen).total_seconds() / 60.0)

    async def _safe(self, coro: Awaitable[_T], default: _T, label: str) -> _T:
        try:
            return await coro
        except Exception as exc:  # any source failure degrades to doubt
            _logger.warning("assemble_step_failed", step=label, error=str(exc))
            return default

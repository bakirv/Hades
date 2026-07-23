"""Wallet cluster detector — funding-graph clustering of the top holders.

The core insight: wallets funded by the *same* source are almost always one
operator splitting a position across many addresses to look decentralised. This
detector fetches the funders of a token's top holders (bounded by an RPC budget)
and groups holders that share a funder. Clusters that control a large combined
share of supply are the real concentration risk that a naive holder count hides.

Cost is strictly capped: only the top ``max_holders`` are inspected and each
funder lookup is itself bounded inside the reader. When the budget stops the
search short, the report is marked ``data_complete=False`` so the analyzer treats
the gap as doubt. The :class:`NullClusterDetector` disables the feature entirely.
"""

from __future__ import annotations

from collections import defaultdict

from hades.contexts.common.domain.value_objects import TokenRef
from hades.contexts.security.domain.models import (
    ClusterReport,
    HolderBalance,
    WalletCluster,
)
from hades.contexts.security.domain.ports import OnChainReader
from hades.shared_kernel.logging import get_logger

_logger = get_logger("security.cluster")


class FundingGraphClusterDetector:
    """Clusters top holders by their common funding wallet."""

    def __init__(
        self,
        reader: OnChainReader,
        *,
        max_holders: int = 12,
        min_members: int = 3,
    ) -> None:
        self._reader = reader
        self._max_holders = max_holders
        self._min_members = min_members

    async def detect(self, token: TokenRef, holders: list[HolderBalance]) -> ClusterReport:
        sample = sorted(holders, key=lambda h: h.pct, reverse=True)[: self._max_holders]
        funder_to_holders: dict[str, list[HolderBalance]] = defaultdict(list)
        analysed = 0
        complete = len(sample) >= len(holders)
        for holder in sample:
            try:
                funders = await self._reader.get_funders(holder.owner)
            except Exception as exc:  # a lookup failure just lowers coverage
                _logger.warning("funder_lookup_failed", owner=holder.owner, error=str(exc))
                complete = False
                continue
            analysed += 1
            for funder in funders:
                funder_to_holders[funder].append(holder)

        clusters: list[WalletCluster] = []
        for funder, members in funder_to_holders.items():
            unique = {m.owner: m for m in members}.values()
            if len(unique) >= self._min_members:
                clusters.append(
                    WalletCluster(
                        members=tuple(m.owner for m in unique),
                        funder=funder,
                        pct_supply=sum(m.pct for m in unique),
                        reason="common_funder",
                    )
                )
        return ClusterReport(
            clusters=tuple(clusters),
            analysed_wallets=analysed,
            data_complete=complete,
        )


class NullClusterDetector:
    """Disabled detector — returns an empty, complete report (feature off)."""

    async def detect(self, token: TokenRef, holders: list[HolderBalance]) -> ClusterReport:
        return ClusterReport(clusters=(), analysed_wallets=0, data_complete=True)

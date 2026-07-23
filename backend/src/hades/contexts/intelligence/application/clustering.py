"""Cluster Builder — collapse coordinated wallets into single entities.

Fifty wallets funded by the same source, buying the same token in the same window
in the same sizes are almost certainly one operator wearing fifty masks. Treating
them as fifty independent holders badly understates concentration risk. This
builder groups the observed wallets by shared funding (the strongest cheap
signal) and assigns each group a stable ``cluster_id`` and an explicit confidence.

Pure and deterministic: it clusters over the observation batch, doing no I/O.
Clustering is probabilistic — every cluster carries the confidence and the reason
behind it, so a human can always challenge it.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict

from hades.contexts.intelligence.domain.models import Cluster, WalletObservationBatch


class ClusterBuilder:
    """Groups a token's observed wallets into likely single-entity clusters."""

    def __init__(self, *, min_members: int = 3) -> None:
        self._min_members = min_members

    def build(self, batch: WalletObservationBatch) -> tuple[Cluster, ...]:
        # Map each funder to the set of wallets it funded within this batch.
        by_funder: dict[str, set[str]] = defaultdict(set)
        pct_by_wallet: dict[str, float] = {}
        for obs in batch.observations:
            pct_by_wallet[obs.address] = max(pct_by_wallet.get(obs.address, 0.0), obs.pct_supply)
            for funder in obs.funders:
                by_funder[funder].add(obs.address)

        clusters: list[Cluster] = []
        for funder, members in by_funder.items():
            if len(members) < self._min_members:
                continue
            ordered = tuple(sorted(members))
            pct = sum(pct_by_wallet.get(m, 0.0) for m in ordered)
            clusters.append(
                Cluster(
                    cluster_id=_cluster_id(funder, ordered),
                    members=ordered,
                    funder=funder,
                    reason="common_funder",
                    confidence=_confidence(len(ordered)),
                    pct_supply=round(pct, 4),
                )
            )
        # Largest / most concentrated clusters first.
        clusters.sort(key=lambda c: (c.pct_supply, c.size), reverse=True)
        return tuple(clusters)


def _confidence(size: int) -> float:
    """Bigger coordinated groups are less likely to be coincidence."""
    return min(0.95, 0.4 + 0.1 * size)


def _cluster_id(funder: str, members: tuple[str, ...]) -> str:
    digest = hashlib.sha1(("|".join((funder, *members))).encode()).hexdigest()
    return f"cl_{digest[:16]}"

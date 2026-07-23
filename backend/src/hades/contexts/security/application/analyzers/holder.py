"""Holder Analyzer — how is ownership distributed?

Counting holders is not enough. A token with 5,000 holders where one wallet owns
40% of supply is a time-bomb. This analyzer measures *inequality*, not headcount:

* Top-1 and Top-10 concentration.
* **HHI** (Herfindahl-Hirschman Index) — the sum of squared supply shares; high
  HHI means a few wallets dominate.
* **Gini coefficient** — overall inequality of the holder distribution.

Known non-owner accounts (the pool vault, burn addresses) are excluded from the
concentration figures so locked/burned supply is never mistaken for a whale.
"""

from __future__ import annotations

from hades.contexts.security.application.analyzers.base import (
    build_report,
    flag,
    positive,
)
from hades.contexts.security.domain.models import (
    AnalyzerReport,
    HolderBalance,
    RiskSeverity,
    SecurityInputs,
)

# Addresses that hold supply but are not "owners" for concentration purposes.
_BURN_ADDRESSES = frozenset(
    {
        "1nc1nerator11111111111111111111111111111111",  # incinerator
        "11111111111111111111111111111111",  # system program
    }
)


def gini(amounts: list[float]) -> float:
    """Gini coefficient of a list of non-negative amounts, in [0, 1].

    0 = perfect equality, 1 = one wallet owns everything. Uses the standard
    mean-absolute-difference formulation, robust to a partial (top-N) sample.
    """
    values = sorted(a for a in amounts if a > 0)
    n = len(values)
    if n == 0:
        return 0.0
    cumulative = 0.0
    for i, value in enumerate(values, start=1):
        cumulative += i * value
    total = sum(values)
    if total == 0:
        return 0.0
    return (2.0 * cumulative) / (n * total) - (n + 1.0) / n


def hhi(shares_pct: list[float]) -> float:
    """Herfindahl-Hirschman Index over supply shares (%). Returns [0, 1]."""
    return sum((p / 100.0) ** 2 for p in shares_pct)


class HolderAnalyzer:
    """Judges ownership concentration and inequality."""

    def __init__(
        self,
        *,
        max_top1_pct: float = 25.0,
        max_top10_pct: float = 60.0,
        min_holders: int = 50,
    ) -> None:
        self._max_top1 = max_top1_pct
        self._max_top10 = max_top10_pct
        self._min_holders = min_holders

    @property
    def name(self) -> str:
        return "holder"

    def analyze(self, inputs: SecurityInputs) -> AnalyzerReport:
        owned = self._owner_holders(inputs)
        if not owned:
            return build_report(
                self.name,
                flags=[
                    flag(
                        "NO_HOLDER_DATA",
                        RiskSeverity.HIGH,
                        "No holder distribution available.",
                    )
                ],
                insufficient_data=True,
            )

        shares = [h.pct for h in owned]
        top1 = max(shares)
        top10 = sum(sorted(shares, reverse=True)[:10])
        index_hhi = hhi(shares)
        index_gini = gini([float(h.amount) for h in owned])
        count = inputs.holder_count

        facts: dict[str, object] = {
            "top1_pct": round(top1, 2),
            "top10_pct": round(top10, 2),
            "hhi": round(index_hhi, 4),
            "gini": round(index_gini, 4),
            "holder_count": count,
            "top_holders": [{"owner": h.owner, "pct": round(h.pct, 2)} for h in owned[:10]],
        }

        flags = []
        positives = []

        if top1 >= 50.0:
            flags.append(
                flag(
                    "SINGLE_WALLET_MAJORITY",
                    RiskSeverity.CRITICAL,
                    f"Top holder controls {top1:.1f}% of supply.",
                )
            )
        elif top1 >= self._max_top1:
            flags.append(
                flag(
                    "HIGH_TOP_HOLDER",
                    RiskSeverity.HIGH,
                    f"Top holder controls {top1:.1f}% of supply (max {self._max_top1:.0f}%).",
                )
            )

        if top10 >= self._max_top10:
            flags.append(
                flag(
                    "WHALE_DOMINANCE",
                    RiskSeverity.HIGH,
                    f"Top 10 holders control {top10:.1f}% of supply.",
                )
            )

        if index_hhi >= 0.25:
            flags.append(
                flag(
                    "HIGH_CONCENTRATION_HHI",
                    RiskSeverity.MEDIUM,
                    f"Ownership is highly concentrated (HHI {index_hhi:.2f}).",
                )
            )

        if count is not None and count < self._min_holders:
            flags.append(
                flag(
                    "FEW_HOLDERS",
                    RiskSeverity.MEDIUM,
                    f"Only {count} holders (min {self._min_holders}).",
                )
            )

        if not flags:
            positives.append(
                positive(
                    "HEALTHY_DISTRIBUTION",
                    f"Well-distributed supply (top holder {top1:.1f}%, Gini {index_gini:.2f}).",
                )
            )

        return build_report(self.name, flags=flags, positives=positives, facts=facts)

    def _owner_holders(self, inputs: SecurityInputs) -> list[HolderBalance]:
        """Top holders excluding the pool vault and burn addresses."""
        pool_addr = inputs.pool.address if inputs.pool else None
        excluded = set(_BURN_ADDRESSES)
        if pool_addr:
            excluded.add(pool_addr)
        return [h for h in inputs.holders if h.owner not in excluded]

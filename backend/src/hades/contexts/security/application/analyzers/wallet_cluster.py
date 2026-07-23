"""Wallet Cluster Analyzer — how many of these "holders" are one person?

Distribution figures lie when a single entity splits its holdings across dozens
of wallets. This analyzer works on the :class:`ClusterReport` the infrastructure
built (by tracing the funding graph of the top holders — wallets funded by the
same source, in the same window, are almost certainly one operator). A cluster
that quietly controls a large share of supply is a coordinated dump waiting to
happen, and is far more dangerous than the same supply held by one visible whale.

When the funding search was bounded (RPC budget), the report says so and the
analyzer treats the gap as doubt.
"""

from __future__ import annotations

from hades.contexts.security.application.analyzers.base import (
    build_report,
    flag,
    positive,
)
from hades.contexts.security.domain.models import (
    AnalyzerReport,
    RiskSeverity,
    SecurityInputs,
)


class WalletClusterAnalyzer:
    """Judges coordinated ownership hidden behind many wallets."""

    def __init__(
        self,
        *,
        critical_cluster_pct: float = 40.0,
        high_cluster_pct: float = 20.0,
        min_cluster_members: int = 3,
    ) -> None:
        self._critical_pct = critical_cluster_pct
        self._high_pct = high_cluster_pct
        self._min_members = min_cluster_members

    @property
    def name(self) -> str:
        return "wallet_cluster"

    def analyze(self, inputs: SecurityInputs) -> AnalyzerReport:
        report = inputs.cluster
        if report is None:
            return build_report(
                self.name,
                flags=[
                    flag(
                        "CLUSTER_ANALYSIS_UNAVAILABLE",
                        RiskSeverity.LOW,
                        "Wallet-cluster analysis was not run.",
                    )
                ],
                insufficient_data=True,
            )

        clusters = [c for c in report.clusters if len(c.members) >= self._min_members]
        largest = report.largest_pct
        facts: dict[str, object] = {
            "cluster_count": len(clusters),
            "largest_cluster_pct": round(largest, 2),
            "analysed_wallets": report.analysed_wallets,
            "data_complete": report.data_complete,
            "clusters": [
                {
                    "members": len(c.members),
                    "pct_supply": round(c.pct_supply, 2),
                    "funder": c.funder,
                }
                for c in clusters
            ],
        }
        flags = []
        positives = []

        if largest >= self._critical_pct:
            flags.append(
                flag(
                    "CLUSTER_CONTROLS_SUPPLY",
                    RiskSeverity.CRITICAL,
                    f"A single wallet cluster controls {largest:.1f}% of supply.",
                )
            )
        elif largest >= self._high_pct:
            flags.append(
                flag(
                    "WALLET_CLUSTER_DETECTED",
                    RiskSeverity.HIGH,
                    f"A wallet cluster controls {largest:.1f}% of supply.",
                )
            )
        elif clusters:
            flags.append(
                flag(
                    "MINOR_CLUSTER",
                    RiskSeverity.LOW,
                    f"{len(clusters)} small wallet cluster(s) detected.",
                )
            )
        elif report.data_complete:
            positives.append(
                positive("NO_CLUSTERS", "No coordinated wallet clusters found among top holders.")
            )

        if not report.data_complete:
            flags.append(
                flag(
                    "CLUSTER_SEARCH_BOUNDED",
                    RiskSeverity.INFO,
                    "Funding-graph search was bounded by RPC budget — coverage partial.",
                )
            )

        return build_report(self.name, flags=flags, positives=positives, facts=facts)

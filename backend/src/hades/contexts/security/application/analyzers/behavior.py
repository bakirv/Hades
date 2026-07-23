"""Behavior Analyzer — does the crowd's behaviour make sense?

Where the Transaction Analyzer inspects the mechanics of individual trades, this
one reads the *aggregate psychology* of the flow:

* Everyone buys, nobody sells — classic accumulation before a coordinated dump
  (or an inability to sell at all).
* Enormous volume driven by a handful of participants — manufactured hype.
* Overwhelmingly one-sided flow — an orchestrated pump.

It reasons over the buyer/seller balance the Feature Engine computes and stays
neutral (no penalty, no reward) when there is not yet enough activity to judge —
a brand-new token legitimately has few trades.
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


class BehaviorAnalyzer:
    """Judges buyer/seller flow for coordinated or one-sided behaviour."""

    def __init__(
        self,
        *,
        min_trades_to_judge: float = 20.0,
        one_sided_ratio: float = 12.0,
    ) -> None:
        self._min_trades = min_trades_to_judge
        self._one_sided = one_sided_ratio

    @property
    def name(self) -> str:
        return "behavior"

    def analyze(self, inputs: SecurityInputs) -> AnalyzerReport:
        f = inputs.features
        buyers = f.get("basic.buyers")
        sellers = f.get("basic.sellers")
        trades = f.get("basic.trades_1h") or f.get("basic.trades_5m")

        if buyers is None and sellers is None:
            return build_report(
                self.name,
                flags=[
                    flag(
                        "BEHAVIOR_DATA_INSUFFICIENT",
                        RiskSeverity.INFO,
                        "No buyer/seller features available yet.",
                    )
                ],
                insufficient_data=True,
            )

        # Not enough activity to draw conclusions — stay neutral, don't punish.
        if trades is not None and trades < self._min_trades:
            return build_report(
                self.name,
                flags=[
                    flag(
                        "TOO_EARLY_TO_JUDGE",
                        RiskSeverity.INFO,
                        f"Only {trades:.0f} trades so far — behaviour inconclusive.",
                    )
                ],
                facts={"buyers": buyers, "sellers": sellers, "trades": trades},
                insufficient_data=True,
                base=90.0,
            )

        buyers = buyers or 0.0
        sellers = sellers or 0.0
        flags = []
        positives = []
        facts: dict[str, object] = {
            "buyers": buyers,
            "sellers": sellers,
            "trades": trades,
        }

        # Everyone buys, nobody sells: accumulation / un-sellable pattern.
        if buyers >= 30 and sellers == 0:
            flags.append(
                flag(
                    "NO_SELLERS",
                    RiskSeverity.HIGH,
                    f"{buyers:.0f} buyers and zero sellers — nobody has exited.",
                )
            )
        # Wildly one-sided flow: orchestrated pump.
        elif sellers > 0 and buyers / max(sellers, 1.0) >= self._one_sided:
            flags.append(
                flag(
                    "ONE_SIDED_BUYING",
                    RiskSeverity.MEDIUM,
                    f"Buyers outnumber sellers {buyers / max(sellers, 1.0):.0f}:1 — "
                    "possible coordinated pump.",
                )
            )
        else:
            positives.append(
                positive("BALANCED_FLOW", "Two-sided trading with real buyers and sellers.")
            )

        return build_report(self.name, flags=flags, positives=positives, facts=facts)

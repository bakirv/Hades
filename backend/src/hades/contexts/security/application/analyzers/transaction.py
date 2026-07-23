"""Transaction Analyzer — do the trades themselves look organic?

Looks for mechanical footprints of manipulation in the trade flow the Feature
Engine already measured: wash trading (lots of volume, almost no unique buyers),
recurring wallets churning the same coins, and volume that is not backed by real
participants. It does not need raw signature history for these tells — the
aggregated features expose them — and it degrades to "insufficient data" when the
features are not yet available rather than guessing.
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


class TransactionAnalyzer:
    """Judges wash trading and non-organic transaction patterns."""

    def __init__(
        self,
        *,
        wash_volume_per_buyer_usd: float = 5_000.0,
        high_recurring_ratio: float = 0.6,
    ) -> None:
        self._wash_vpb = wash_volume_per_buyer_usd
        self._high_recurring = high_recurring_ratio

    @property
    def name(self) -> str:
        return "transaction"

    def analyze(self, inputs: SecurityInputs) -> AnalyzerReport:
        f = inputs.features
        volume = f.get("basic.volume")
        buyers = f.get("basic.buyers")
        recurring_ratio = f.get("holders.recurring_ratio")

        if volume is None and buyers is None and recurring_ratio is None:
            return build_report(
                self.name,
                flags=[
                    flag(
                        "TX_DATA_INSUFFICIENT",
                        RiskSeverity.INFO,
                        "No transaction features available yet.",
                    )
                ],
                insufficient_data=True,
            )

        flags = []
        positives = []
        facts: dict[str, object] = {
            "volume_usd": volume,
            "unique_buyers": buyers,
            "recurring_ratio": recurring_ratio,
        }

        # Wash trading: heavy volume concentrated in very few unique buyers.
        if volume is not None and buyers is not None and buyers > 0:
            volume_per_buyer = volume / buyers
            facts["volume_per_buyer_usd"] = round(volume_per_buyer, 2)
            if volume >= self._wash_vpb and volume_per_buyer >= self._wash_vpb:
                flags.append(
                    flag(
                        "WASH_TRADING_SUSPECTED",
                        RiskSeverity.HIGH,
                        f"${volume:,.0f} volume across only {buyers:.0f} unique buyer(s).",
                    )
                )
        elif volume is not None and volume > self._wash_vpb and (buyers or 0) == 0:
            flags.append(
                flag(
                    "VOLUME_WITHOUT_BUYERS",
                    RiskSeverity.HIGH,
                    f"${volume:,.0f} volume with no unique buyers — self-trading.",
                )
            )

        # Recurring wallets churning the token (bot loops).
        if recurring_ratio is not None and recurring_ratio >= self._high_recurring:
            flags.append(
                flag(
                    "HIGH_RECURRING_WALLETS",
                    RiskSeverity.MEDIUM,
                    f"{recurring_ratio:.0%} of activity is the same recurring wallets.",
                )
            )

        if not flags:
            positives.append(
                positive("ORGANIC_FLOW", "Transaction flow shows no manipulation footprint.")
            )

        return build_report(self.name, flags=flags, positives=positives, facts=facts)

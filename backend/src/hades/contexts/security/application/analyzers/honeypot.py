"""Honeypot Analyzer — can you actually sell what you bought?

A honeypot lets you buy but not sell (or taxes the sale to nothing). The
infrastructure layer runs a real buy+sell simulation (a Jupiter route quote in
both directions) and hands the result here as a :class:`HoneypotProbe`. This
analyzer never relies on a single tell: an un-sellable simulation is critical, a
punitive or wildly asymmetric sell tax is a strong flag, and an *unverifiable*
result is treated as doubt rather than a pass.

Belt and braces: an active freeze authority (from the mint account) is itself a
latent honeypot vector, so a still-active freeze reinforces the concern here too.
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

_HIGH_TAX_BPS = 1_000  # 10%
_PUNITIVE_TAX_BPS = 3_000  # 30%


class HoneypotAnalyzer:
    """Judges sellability and transfer taxes from a buy+sell simulation."""

    @property
    def name(self) -> str:
        return "honeypot"

    def analyze(self, inputs: SecurityInputs) -> AnalyzerReport:
        probe = inputs.honeypot
        mint = inputs.mint_account

        if probe is None:
            flags = [
                flag(
                    "HONEYPOT_UNVERIFIED",
                    RiskSeverity.HIGH,
                    "Sell simulation could not be run — sellability unverified.",
                )
            ]
            if mint is not None and not mint.freeze_renounced:
                flags.append(
                    flag(
                        "FREEZE_HONEYPOT_VECTOR",
                        RiskSeverity.HIGH,
                        "Active freeze authority can make the token un-sellable.",
                    )
                )
            return build_report(self.name, flags=flags, insufficient_data=True)

        flags = []
        positives = []
        facts: dict[str, object] = {
            "sellable": probe.sellable,
            "buyable": probe.buyable,
            "buy_tax_bps": probe.buy_tax_bps,
            "sell_tax_bps": probe.sell_tax_bps,
            "note": probe.note,
        }

        if probe.sellable is False:
            flags.append(
                flag(
                    "CANNOT_SELL",
                    RiskSeverity.CRITICAL,
                    "Sell simulation failed — this is a honeypot.",
                )
            )
        elif probe.sellable is None:
            flags.append(
                flag(
                    "SELLABILITY_UNVERIFIED",
                    RiskSeverity.HIGH,
                    "Could not confirm the token is sellable.",
                )
            )

        sell_tax = probe.sell_tax_bps
        if sell_tax is not None:
            if sell_tax >= _PUNITIVE_TAX_BPS:
                flags.append(
                    flag(
                        "PUNITIVE_SELL_TAX",
                        RiskSeverity.CRITICAL,
                        f"Sell tax is {sell_tax / 100:.1f}% — effectively un-sellable.",
                    )
                )
            elif sell_tax >= _HIGH_TAX_BPS:
                flags.append(
                    flag(
                        "HIGH_SELL_TAX",
                        RiskSeverity.HIGH,
                        f"Sell tax is {sell_tax / 100:.1f}%.",
                    )
                )
            buy_tax = probe.buy_tax_bps or 0
            if sell_tax - buy_tax >= _HIGH_TAX_BPS:
                flags.append(
                    flag(
                        "ASYMMETRIC_TAX",
                        RiskSeverity.HIGH,
                        f"Sell tax ({sell_tax / 100:.1f}%) far exceeds buy tax "
                        f"({buy_tax / 100:.1f}%).",
                    )
                )

        if probe.sellable is True and not flags:
            positives.append(
                positive("SELLABLE_VERIFIED", "Buy+sell simulation succeeded — token is sellable.")
            )

        return build_report(self.name, flags=flags, positives=positives, facts=facts)

"""Fee Engine — computes every cost component of a trade.

Network fee (base signature cost), priority fee (the compute-unit bid that gets
a Solana transaction landed under congestion), and the DEX/aggregator fee. Paper
and live share the same estimator so simulated PnL carries the same cost drag as
the real thing — the single biggest reason paper over-states edge is pretending
fees away, so we never do. Jito tip support is scaffolded (off by default).
"""

from __future__ import annotations

from decimal import Decimal

from hades.contexts.execution.domain.models import FeeBreakdown

# 1 SOL = 1e9 lamports = 1e15 microlamports. Base tx fee ≈ 5000 lamports/sig.
_MICROLAMPORTS_PER_SOL = Decimal(10) ** 15
_BASE_FEE_LAMPORTS = Decimal(5000)
_LAMPORTS_PER_SOL = Decimal(10) ** 9


class FeeEngine:
    """Estimates the :class:`FeeBreakdown` for a trade of a given USD notional."""

    def __init__(
        self,
        *,
        priority_fee_microlamports: int = 50_000,
        dex_fee_bps: int = 25,
        sol_price_usd: float = 150.0,
        jito_enabled: bool = False,
        jito_tip_microlamports: int = 0,
    ) -> None:
        self._priority = max(0, priority_fee_microlamports)
        self._dex_fee_bps = max(0, dex_fee_bps)
        self._sol_price = Decimal(str(max(0.0, sol_price_usd)))
        self._jito_enabled = jito_enabled
        self._jito_tip = max(0, jito_tip_microlamports)

    def estimate(self, *, notional_usd: Decimal) -> FeeBreakdown:
        notional = Decimal(str(notional_usd))

        network_sol = _BASE_FEE_LAMPORTS / _LAMPORTS_PER_SOL
        network_usd = network_sol * self._sol_price

        priority_micro = self._priority + (self._jito_tip if self._jito_enabled else 0)
        priority_sol = Decimal(priority_micro) / _MICROLAMPORTS_PER_SOL
        priority_usd = priority_sol * self._sol_price

        dex_usd = notional * Decimal(self._dex_fee_bps) / Decimal(10_000)

        total = network_usd + priority_usd + dex_usd
        return FeeBreakdown(
            network_fee_usd=_q(network_usd),
            priority_fee_usd=_q(priority_usd),
            dex_fee_usd=_q(dex_usd),
            total_usd=_q(total),
            priority_fee_microlamports=priority_micro,
        )


def _q(value: Decimal) -> Decimal:
    """Quantise to 8 dp — enough for sub-cent SOL fees without float noise."""
    return value.quantize(Decimal("0.00000001"))

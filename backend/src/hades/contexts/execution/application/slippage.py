"""Slippage Engine — dynamic, never a fixed constant.

Given the live market context of a fill (liquidity, volatility, spread, position
size, DEX, time of day) it produces a *recommended* slippage tolerance and a
*hard maximum*. The executor cancels a trade whose expected impact exceeds the
order's budget. The engine is pure (no I/O) and conservative: every missing or
adverse input widens the estimate rather than narrowing it, so uncertainty costs
tolerance, never risk.
"""

from __future__ import annotations

from hades.contexts.execution.domain.models import SlippageContext, SlippageEstimate

# Illiquid venues get an extra cushion; unknown venues are treated as illiquid.
_DEX_SURCHARGE_BPS: dict[str, int] = {
    "raydium": 0,
    "orca": 0,
    "meteora": 10,
    "pumpfun": 25,
    "unknown": 25,
}


class SlippageEngine:
    """Scores a :class:`SlippageContext` into a :class:`SlippageEstimate`."""

    def __init__(
        self,
        *,
        base_bps: int = 100,
        hard_max_bps: int = 500,
        size_impact_divisor: float = 0.5,
    ) -> None:
        # ``base_bps`` is the floor tolerance on a healthy, deep pool.
        self._base = max(0, base_bps)
        self._hard_max = max(base_bps, hard_max_bps)
        # Above this fraction of pool liquidity, size dominates the estimate.
        self._size_divisor = max(1e-6, size_impact_divisor)

    def estimate(self, ctx: SlippageContext, *, order_max_bps: int) -> SlippageEstimate:
        reasons: list[str] = []
        bps = float(self._base)

        # --- size-vs-liquidity: the dominant term for meme-coin pools ---------
        if ctx.liquidity_usd > 0 and ctx.notional_usd > 0:
            pool_fraction = ctx.notional_usd / ctx.liquidity_usd
            impact = (pool_fraction / self._size_divisor) * 10_000.0
            if impact > 1.0:
                bps += impact
                reasons.append(f"size {pool_fraction:.1%} of pool")
        elif ctx.notional_usd > 0:
            # No liquidity reading → assume the pool is thin.
            bps += 150.0
            reasons.append("liquidity unknown")

        # --- volatility widens the band ---------------------------------------
        if ctx.volatility_pct > 0:
            bps += min(ctx.volatility_pct, 100.0) * 2.0
            if ctx.volatility_pct >= 20:
                reasons.append(f"volatility {ctx.volatility_pct:.0f}%")

        # --- spread flows straight through ------------------------------------
        if ctx.spread_bps > 0:
            bps += ctx.spread_bps
            if ctx.spread_bps >= 50:
                reasons.append(f"spread {ctx.spread_bps:.0f}bps")

        # --- venue + session surcharges ---------------------------------------
        surcharge = _DEX_SURCHARGE_BPS.get(ctx.dex.lower(), _DEX_SURCHARGE_BPS["unknown"])
        if surcharge:
            bps += surcharge
            reasons.append(f"venue {ctx.dex}")
        if ctx.off_peak:
            bps += 20.0
            reasons.append("off-peak")

        recommended = round(bps)
        max_bps = min(self._hard_max, max(recommended, order_max_bps))
        within = recommended <= order_max_bps
        reason = ", ".join(reasons) if reasons else "healthy conditions"
        return SlippageEstimate(
            recommended_bps=recommended,
            max_bps=max_bps,
            reason=reason,
            within_limits=within,
        )

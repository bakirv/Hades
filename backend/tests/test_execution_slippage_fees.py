"""The Slippage Engine is dynamic and the Fee Engine charges every component."""

from __future__ import annotations

from decimal import Decimal

from hades.contexts.execution.application.fees import FeeEngine
from hades.contexts.execution.application.slippage import SlippageEngine
from hades.contexts.execution.domain.models import SlippageContext


def _slip() -> SlippageEngine:
    return SlippageEngine(base_bps=100, hard_max_bps=500)


def test_healthy_deep_pool_stays_near_base() -> None:
    est = _slip().estimate(
        SlippageContext(liquidity_usd=1_000_000, notional_usd=100, dex="raydium"),
        order_max_bps=300,
    )
    assert est.recommended_bps <= 120
    assert est.within_limits is True


def test_large_size_relative_to_pool_widens_slippage() -> None:
    est = _slip().estimate(
        SlippageContext(liquidity_usd=10_000, notional_usd=5_000, dex="raydium"),
        order_max_bps=300,
    )
    assert est.recommended_bps > 300
    assert est.within_limits is False  # exceeds the order budget


def test_unknown_liquidity_is_treated_as_thin() -> None:
    est = _slip().estimate(SlippageContext(notional_usd=100), order_max_bps=300)
    assert est.recommended_bps > 100
    assert "liquidity unknown" in est.reason


def test_illiquid_venue_and_offpeak_add_surcharge() -> None:
    base = _slip().estimate(
        SlippageContext(liquidity_usd=1_000_000, notional_usd=100, dex="raydium"),
        order_max_bps=300,
    )
    worse = _slip().estimate(
        SlippageContext(liquidity_usd=1_000_000, notional_usd=100, dex="pumpfun", off_peak=True),
        order_max_bps=300,
    )
    assert worse.recommended_bps > base.recommended_bps


def test_max_bps_never_exceeds_hard_ceiling() -> None:
    est = _slip().estimate(
        SlippageContext(liquidity_usd=1_000, notional_usd=100_000, dex="unknown"),
        order_max_bps=100_000,
    )
    assert est.max_bps <= 500


def test_fee_engine_sums_all_components() -> None:
    fees = FeeEngine(priority_fee_microlamports=50_000, dex_fee_bps=25, sol_price_usd=150.0)
    breakdown = fees.estimate(notional_usd=Decimal(100))
    assert breakdown.dex_fee_usd == Decimal("0.25000000")  # 25 bps of 100
    assert breakdown.network_fee_usd > 0
    assert breakdown.total_usd == (
        breakdown.network_fee_usd + breakdown.priority_fee_usd + breakdown.dex_fee_usd
    )
    assert breakdown.priority_fee_microlamports == 50_000


def test_dex_fee_scales_with_notional() -> None:
    fees = FeeEngine(dex_fee_bps=25, sol_price_usd=150.0)
    small = fees.estimate(notional_usd=Decimal(10))
    big = fees.estimate(notional_usd=Decimal(1_000))
    assert big.dex_fee_usd == small.dex_fee_usd * 100


def test_jito_tip_only_counts_when_enabled() -> None:
    off = FeeEngine(
        priority_fee_microlamports=50_000, jito_enabled=False, jito_tip_microlamports=1_000_000
    )
    on = FeeEngine(
        priority_fee_microlamports=50_000, jito_enabled=True, jito_tip_microlamports=1_000_000
    )
    assert on.estimate(notional_usd=Decimal(100)).priority_fee_microlamports == 1_050_000
    assert off.estimate(notional_usd=Decimal(100)).priority_fee_microlamports == 50_000

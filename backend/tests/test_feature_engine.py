"""Feature Engine: indicators, extractor blocks, and the composing engine."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from hades.contexts.common.domain.value_objects import TokenMint, TokenRef
from hades.contexts.features.application import indicators as ind
from hades.contexts.features.application.extractors import DEFAULT_BLOCKS
from hades.contexts.features.application.feature_engine import FeatureEngine
from hades.contexts.features.domain.events import FeaturesComputed
from hades.contexts.features.domain.models import (
    FeatureInputs,
    HolderInfo,
    MarketPoint,
    PoolInfo,
)
from hades.contexts.features.infrastructure.feature_store import InMemoryFeatureStore
from hades.shared_kernel.events import InMemoryEventBus

_MINT = "A" * 44


def _token() -> TokenRef:
    return TokenRef(mint=TokenMint(address=_MINT))


def _inputs() -> FeatureInputs:
    now = datetime.now(UTC)
    history = tuple(
        MarketPoint(
            at=now - timedelta(minutes=10 - i),
            price=1.0 + i * 0.1,
            volume=100.0 + i,
            liquidity=5000.0 + i * 10,
            buys=i,
            sells=1,
        )
        for i in range(10)
    )
    return FeatureInputs(
        token=_token(),
        now=now,
        created_at=now - timedelta(minutes=30),
        first_swap_at=now - timedelta(minutes=25),
        price=2.0,
        market_cap=100_000,
        fdv=120_000,
        liquidity=6000,
        volume=1500,
        buy_volume=1000,
        sell_volume=500,
        buyers=20,
        sellers=10,
        trades_1m=5,
        trades_1h=60,
        history=history,
        holders=HolderInfo(count=100, prev_count=80, recurring_wallets=40, top10_share_pct=35.0),
        pool=PoolInfo(size_usd=6000, lp_locked=True, lock_duration_seconds=86400),
    )


# -- indicators ---------------------------------------------------------------


def test_sma_and_ema() -> None:
    assert ind.sma([1, 2, 3, 4], 2) == 3.5
    assert ind.ema([1, 1, 1], 3) == 1.0


def test_rsi_bounds() -> None:
    rising = list(range(1, 30))
    assert ind.rsi(rising, 14) == 100.0
    assert 0.0 <= ind.rsi([1, 2, 1, 2, 1, 2] * 5, 14) <= 100.0


def test_slope_sign() -> None:
    assert ind.slope([1, 2, 3, 4]) > 0
    assert ind.slope([4, 3, 2, 1]) < 0


def test_short_series_is_safe() -> None:
    assert ind.macd([1.0]) == 0.0
    assert ind.volatility([]) == 0.0
    assert ind.vwap([2.0, 4.0], [0.0, 0.0]) == 3.0  # falls back to SMA when no volume


# -- extractor blocks ---------------------------------------------------------


def test_every_block_returns_finite_values() -> None:
    inputs = _inputs()
    for block in DEFAULT_BLOCKS:
        values = block.compute(inputs)
        assert values, f"{block.namespace} produced nothing"
        assert all(math.isfinite(v) for v in values.values())


def test_basic_age_and_ratios() -> None:
    values = _inputs()
    from hades.contexts.features.application.extractors.basic import BasicFeatures

    out = BasicFeatures().compute(values)
    assert out["age_seconds"] > 0
    assert out["buyer_seller_ratio"] == 2.0


def test_blocks_have_unique_namespaces() -> None:
    namespaces = [b.namespace for b in DEFAULT_BLOCKS]
    assert len(namespaces) == len(set(namespaces))


# -- engine -------------------------------------------------------------------


async def test_engine_computes_stores_and_emits() -> None:
    store = InMemoryFeatureStore()
    bus = InMemoryEventBus()
    events: list[FeaturesComputed] = []
    counts: list[int] = []

    async def on_event(event: object) -> None:
        assert isinstance(event, FeaturesComputed)
        events.append(event)

    bus.subscribe(FeaturesComputed.__name__, on_event)
    engine = FeatureEngine(
        store, event_bus=bus, schema_version=3, on_computed=counts.append
    )
    result = await engine.compute(_inputs())

    assert result.schema_version == 3
    assert result.values  # hundreds of namespaced features
    assert all("." in key for key in result.values)  # namespaced
    assert all(math.isfinite(v) for v in result.values.values())
    stored = await store.latest(_token())
    assert stored is not None
    assert stored.values == result.values
    assert len(events) == 1
    assert events[0].feature_count == len(result.values)
    assert counts == [len(result.values)]

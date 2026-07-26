"""The price oracle: what a token is worth, or an honest ``None``.

With no oracle wired, paper fills are priced at $1 and open positions can never
be marked. With a *dishonest* one they are priced at whatever the thinnest pool
last printed. Both failure modes are covered here.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import httpx

from hades.contexts.common.domain.value_objects import TokenMint, TokenRef
from hades.contexts.execution.infrastructure.price_oracle import (
    DexScreenerPriceOracle,
    StaticPriceOracle,
)

_MINT = "So11111111111111111111111111111111111111112"


def _token() -> TokenRef:
    return TokenRef(mint=TokenMint(address=_MINT), symbol="WSOL")


def _oracle(handler: Any, **kwargs: Any) -> DexScreenerPriceOracle:
    return DexScreenerPriceOracle(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), **kwargs
    )


def _json(payload: dict[str, Any]):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return handler


def _pair(price: str, liquidity: float | None) -> dict[str, Any]:
    pair: dict[str, Any] = {"priceUsd": price}
    if liquidity is not None:
        pair["liquidity"] = {"usd": liquidity}
    return pair


async def test_a_price_is_read_from_the_response() -> None:
    oracle = _oracle(_json({"pairs": [_pair("0.0042", 50_000)]}))

    assert await oracle.price_usd(_token()) == Decimal("0.0042")


async def test_the_price_comes_from_the_deepest_pool() -> None:
    # A thin pool's last trade is the number easiest for someone else to move;
    # marking a book against it would let a few dollars swing our equity.
    oracle = _oracle(
        _json(
            {
                "pairs": [
                    _pair("9.99", 100.0),  # thin and wrong
                    _pair("1.00", 900_000.0),  # deep and right
                    _pair("5.00", 5_000.0),
                ]
            }
        )
    )

    assert await oracle.price_usd(_token()) == Decimal("1.00")


async def test_an_http_error_yields_no_price_rather_than_an_exception() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    assert await _oracle(handler).price_usd(_token()) is None


async def test_a_transport_failure_yields_no_price() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    assert await _oracle(handler).price_usd(_token()) is None


async def test_an_empty_or_malformed_payload_yields_no_price() -> None:
    assert await _oracle(_json({"pairs": []})).price_usd(_token()) is None
    assert await _oracle(_json({})).price_usd(_token()) is None


async def test_a_non_numeric_or_zero_price_is_not_used() -> None:
    oracle = _oracle(_json({"pairs": [_pair("not-a-number", 10.0), _pair("0", 10.0)]}))

    assert await oracle.price_usd(_token()) is None


async def test_a_pair_without_liquidity_is_still_usable() -> None:
    # Missing depth ranks last, but one priced pair is better than no price.
    oracle = _oracle(_json({"pairs": [_pair("3.50", None)]}))

    assert await oracle.price_usd(_token()) == Decimal("3.50")


async def test_prices_are_cached_so_a_book_of_positions_is_one_call() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"pairs": [_pair("2.00", 10_000)]})

    oracle = _oracle(handler, ttl_seconds=60.0)
    for _ in range(5):
        assert await oracle.price_usd(_token()) == Decimal("2.00")

    assert len(calls) == 1


async def test_a_zero_ttl_disables_the_cache() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"pairs": [_pair("2.00", 10_000)]})

    oracle = _oracle(handler, ttl_seconds=0.0)
    await oracle.price_usd(_token())
    await oracle.price_usd(_token())

    assert len(calls) == 2


async def test_the_static_oracle_reports_only_what_it_was_given() -> None:
    oracle = StaticPriceOracle({_MINT: Decimal("7")})

    assert await oracle.price_usd(_token()) == Decimal("7")
    other = TokenRef(mint=TokenMint(address="11111111111111111111111111111111"))
    assert await oracle.price_usd(other) is None

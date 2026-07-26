"""The Paper Executor simulates a realistic fill with costs, never ideal prices."""

from __future__ import annotations

from decimal import Decimal

from hades.contexts.common.domain.value_objects import Money, TokenMint, TokenRef
from hades.contexts.execution.application.fees import FeeEngine
from hades.contexts.execution.application.paper_executor import PaperExecutor
from hades.contexts.execution.application.slippage import SlippageEngine
from hades.contexts.execution.domain.models import OrderRequest, OrderSide, OrderStatus

_MINT = "So11111111111111111111111111111111111111112"


def _token() -> TokenRef:
    return TokenRef(mint=TokenMint(address=_MINT), symbol="WSOL")


def _executor(*, oracle: object | None = None) -> PaperExecutor:
    return PaperExecutor(
        slippage_engine=SlippageEngine(base_bps=100, hard_max_bps=500),
        fee_engine=FeeEngine(sol_price_usd=150.0),
        price_oracle=oracle,  # type: ignore[arg-type]
        latency_ms=0,  # keep the test fast
    )


def _request(side: OrderSide = OrderSide.BUY) -> OrderRequest:
    return OrderRequest(
        token=_token(),
        side=side,
        notional=Money(amount=Decimal(100)),
        max_slippage_bps=300,
    )


async def test_paper_fill_is_filled_with_costs() -> None:
    fill = await _executor().execute(_request())
    assert fill.status is OrderStatus.FILLED
    assert fill.mode == "paper"
    assert fill.fees.amount > 0
    assert fill.slippage_bps > 0
    assert fill.signature is not None and fill.signature.startswith("paper-")
    assert fill.confirmation is not None and fill.confirmation.confirmed is True


async def test_buy_slippage_pushes_price_above_reference() -> None:
    class _Oracle:
        async def price_usd(self, token: TokenRef) -> Decimal:
            return Decimal(2)

    fill = await _executor(oracle=_Oracle()).execute(_request(OrderSide.BUY))
    # A BUY pays *above* the reference price of 2 because slippage works against it.
    assert fill.average_price.amount > Decimal(2)
    # Quantity is notional / effective price → below 50 (=100/2) after slippage.
    assert fill.filled_quantity < Decimal(50)


async def test_sell_slippage_pushes_price_below_reference() -> None:
    class _Oracle:
        async def price_usd(self, token: TokenRef) -> Decimal:
            return Decimal(2)

    fill = await _executor(oracle=_Oracle()).execute(_request(OrderSide.SELL))
    assert fill.average_price.amount < Decimal(2)


async def test_a_buy_spends_exactly_the_order_size() -> None:
    # A BUY is denominated in the cash you commit: slippage buys fewer tokens
    # for it, but the cash out is the order size.
    fill = await _executor().execute(_request(OrderSide.BUY))
    assert fill.notional is not None
    assert fill.notional.amount == Decimal(100)


async def test_a_sell_receives_less_than_the_order_size_because_of_slippage() -> None:
    # A SELL is denominated in the market value of what is being sold, so the
    # impact has to come off the *proceeds*. Modelling it like a buy would make
    # exit slippage free, and a simulation that hands you a costless exit reports
    # profits the real market would never have paid.
    class _Oracle:
        async def price_usd(self, token: TokenRef) -> Decimal:
            return Decimal(2)

    fill = await _executor(oracle=_Oracle()).execute(_request(OrderSide.SELL))

    assert fill.notional is not None
    assert fill.notional.amount < Decimal(100)
    # The tokens given up are valued at the mark, not at the slipped price.
    assert fill.filled_quantity == Decimal(50)
    # Proceeds are those tokens at the price actually achieved.
    assert fill.notional.amount == fill.filled_quantity * fill.average_price.amount


async def test_a_flat_round_trip_loses_money_in_the_simulation() -> None:
    # Buying and selling at one unchanged price must cost something. If the two
    # notionals came back equal, paper mode would be reporting a free round trip.
    class _Oracle:
        async def price_usd(self, token: TokenRef) -> Decimal:
            return Decimal(2)

    executor = _executor(oracle=_Oracle())
    buy = await executor.execute(_request(OrderSide.BUY))
    sell = await executor.execute(_request(OrderSide.SELL))

    assert buy.notional is not None and sell.notional is not None
    assert sell.notional.amount < buy.notional.amount


async def test_no_oracle_falls_back_to_unit_price() -> None:
    fill = await _executor().execute(_request())
    # Unit reference price (1) plus BUY slippage → effective price slightly > 1.
    assert fill.average_price.amount > Decimal(1)
    assert fill.filled_quantity < Decimal(100)


async def test_paper_never_produces_a_live_signature() -> None:
    fill = await _executor().execute(_request())
    assert not (fill.signature or "").startswith("live")
    assert fill.confirmation is not None and fill.confirmation.rpc_url == "paper"

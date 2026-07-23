"""Event bus + event store behave to contract."""

from __future__ import annotations

import pytest

from hades.contexts.common.domain.value_objects import Money, TokenMint, TokenRef
from hades.contexts.scanner.domain.events import TokenDiscovered
from hades.shared_kernel.domain.identifiers import new_id
from hades.shared_kernel.errors import ConcurrencyError
from hades.shared_kernel.events import InMemoryEventBus, InMemoryEventStore

_MINT = "So11111111111111111111111111111111111111112"


def _event() -> TokenDiscovered:
    token = TokenRef(mint=TokenMint(address=_MINT), symbol="WSOL")
    return TokenDiscovered(
        aggregate_id=new_id(),
        token=token,
        source="pumpfun",
        initial_liquidity=Money(amount="10000"),
    )


async def test_bus_delivers_to_subscriber() -> None:
    bus = InMemoryEventBus()
    received: list[str] = []

    async def handler(event: object) -> None:
        received.append(type(event).__name__)

    bus.subscribe("TokenDiscovered", handler)
    await bus.publish(_event())
    assert received == ["TokenDiscovered"]


async def test_store_appends_and_versions() -> None:
    store = InMemoryEventStore()
    aggregate_id = new_id()
    event = _event().model_copy(update={"aggregate_id": aggregate_id})

    await store.append(aggregate_id, "token", [event], expected_version=0)
    stream = await store.load_stream(aggregate_id)
    assert len(stream) == 1
    assert stream[0].version == 1


async def test_store_rejects_stale_version() -> None:
    store = InMemoryEventStore()
    aggregate_id = new_id()
    event = _event().model_copy(update={"aggregate_id": aggregate_id})
    await store.append(aggregate_id, "token", [event], expected_version=0)

    with pytest.raises(ConcurrencyError):
        await store.append(aggregate_id, "token", [event], expected_version=0)

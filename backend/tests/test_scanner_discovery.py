"""Discovery Engine: dedup, coarse gating, source-health events."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from hades.contexts.common.domain.value_objects import Money, TokenMint, TokenRef
from hades.contexts.scanner.application.discovery_engine import DiscoveryEngine
from hades.contexts.scanner.application.metrics import ScannerMetrics
from hades.contexts.scanner.domain.events import SourceHealthChanged
from hades.contexts.scanner.domain.ports import RawTokenCandidate
from hades.contexts.scanner.infrastructure.seen_registry import InMemorySeenTokenRegistry
from hades.shared_kernel.config.settings import ScannerSettings
from hades.shared_kernel.events import InMemoryEventBus
from hades.shared_kernel.observability import MetricsRegistry

_MINT_A = "A" * 44
_MINT_B = "B" * 44
_MINT_C = "C" * 44


def _candidate(mint: str, liquidity: float, source: str = "test") -> RawTokenCandidate:
    return RawTokenCandidate(
        token=TokenRef(mint=TokenMint(address=mint)),
        source=source,
        liquidity=Money(amount=liquidity),
    )


class FakeSource:
    def __init__(self, name: str, candidates: list[RawTokenCandidate]) -> None:
        self._name = name
        self._candidates = candidates

    @property
    def name(self) -> str:
        return self._name

    async def stream(self) -> AsyncIterator[RawTokenCandidate]:
        for candidate in self._candidates:
            yield candidate
        await asyncio.Event().wait()  # keep the stream open until cancelled


class FailingSource:
    @property
    def name(self) -> str:
        return "boom"

    async def stream(self) -> AsyncIterator[RawTokenCandidate]:
        raise RuntimeError("down")
        yield  # pragma: no cover — makes this an async generator


def _settings(**overrides: object) -> ScannerSettings:
    return ScannerSettings().model_copy(update=overrides)


async def _drive(engine: DiscoveryEngine, seconds: float = 0.05) -> None:
    stop = asyncio.Event()
    task = asyncio.create_task(engine.run(stop))
    await asyncio.sleep(seconds)
    stop.set()
    await task


async def _collect(
    candidates: list[RawTokenCandidate], settings: ScannerSettings
) -> tuple[list[RawTokenCandidate], InMemoryEventBus]:
    sink_items: list[RawTokenCandidate] = []

    async def sink(c: RawTokenCandidate) -> None:
        sink_items.append(c)

    bus = InMemoryEventBus()
    engine = DiscoveryEngine(
        [FakeSource("test", candidates)],
        InMemorySeenTokenRegistry(),
        sink,
        settings=settings,
        event_bus=bus,
        metrics=ScannerMetrics(MetricsRegistry()),
    )
    await _drive(engine)
    return sink_items, bus


async def test_passes_new_candidate_over_min_liquidity() -> None:
    items, _ = await _collect([_candidate(_MINT_A, 9000)], _settings(min_liquidity_usd=5000))
    assert [str(c.token.mint) for c in items] == [_MINT_A]


async def test_rejects_low_liquidity() -> None:
    items, _ = await _collect([_candidate(_MINT_A, 100)], _settings(min_liquidity_usd=5000))
    assert items == []


async def test_dedups_repeated_mint() -> None:
    items, _ = await _collect(
        [_candidate(_MINT_A, 9000), _candidate(_MINT_A, 9000)],
        _settings(min_liquidity_usd=5000),
    )
    assert len(items) == 1


async def test_blacklist_blocks_token() -> None:
    items, _ = await _collect(
        [_candidate(_MINT_A, 9000)],
        _settings(min_liquidity_usd=5000, blacklist_tokens=_MINT_A),
    )
    assert items == []


async def test_whitelist_bypasses_liquidity_gate() -> None:
    items, _ = await _collect(
        [_candidate(_MINT_A, 1)],
        _settings(min_liquidity_usd=5000, whitelist_tokens=_MINT_A),
    )
    assert [str(c.token.mint) for c in items] == [_MINT_A]


async def test_failing_source_emits_source_down_event() -> None:
    events: list[SourceHealthChanged] = []
    bus = InMemoryEventBus()

    async def on_event(event: object) -> None:
        assert isinstance(event, SourceHealthChanged)
        events.append(event)

    bus.subscribe(SourceHealthChanged.__name__, on_event)

    async def sink(c: RawTokenCandidate) -> None:  # pragma: no cover — never called
        pass

    engine = DiscoveryEngine(
        [FailingSource()],
        InMemorySeenTokenRegistry(),
        sink,
        settings=_settings(),
        event_bus=bus,
        metrics=ScannerMetrics(MetricsRegistry()),
    )
    await _drive(engine)
    assert any(not e.available for e in events)

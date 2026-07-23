"""Replay Engine — reconstructs any historical moment, deterministically.

Given a time window, it re-reads the copied historical stream in exact temporal
order and drives a set of shadow strategies through it, reproducing what the
analytical pipeline (scanner → security → intelligence → AI → risk shaping) would
have surfaced — but entirely offline and virtual. Because it consumes copies and
drives only shadow runners, a replay can never place an order or mutate any
production state.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from hades.contexts.research.application.shadow import ShadowStrategyRunner
from hades.contexts.research.domain.models import ShadowStrategy
from hades.contexts.research.domain.ports import HistoricalDataReader, HistoricalSample


@dataclass
class ReplayResult:
    """What a replay observed — counts and the resulting shadow snapshots."""

    from_iso: str
    to_iso: str
    events_replayed: int = 0
    shadows: tuple[ShadowStrategy, ...] = field(default_factory=tuple)


class ReplayEngine:
    """Replays a historical window through a set of shadow strategies."""

    def __init__(self, reader: HistoricalDataReader) -> None:
        self._reader = reader

    async def replay(
        self,
        *,
        from_iso: str,
        to_iso: str,
        shadows: Sequence[ShadowStrategy] = (),
        limit: int = 100_000,
    ) -> ReplayResult:
        samples = await self._reader.load_samples(from_iso=from_iso, to_iso=to_iso, limit=limit)
        return self.replay_samples(
            from_iso=from_iso, to_iso=to_iso, samples=samples, shadows=shadows
        )

    def replay_samples(
        self,
        *,
        from_iso: str,
        to_iso: str,
        samples: Sequence[HistoricalSample],
        shadows: Sequence[ShadowStrategy] = (),
    ) -> ReplayResult:
        runners = [ShadowStrategyRunner(s) for s in shadows]
        for sample in samples:
            for runner in runners:
                runner.observe(sample)
        return ReplayResult(
            from_iso=from_iso,
            to_iso=to_iso,
            events_replayed=len(samples),
            shadows=tuple(r.shadow for r in runners),
        )

"""Feature-inputs assembler adapters.

The Feature Engine needs a cleaned :class:`FeatureInputs` bundle. A full assembler
draws on the Market Engine's snapshots + rolling history; that engine is a later
phase, so this phase ships :class:`HintInputsAssembler`, which seeds the bundle
from the discovery event's liquidity and the current time. It always returns a
valid bundle, so features can be computed from day one and enriched later.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from hades.contexts.common.domain.value_objects import TokenRef
from hades.contexts.features.domain.models import FeatureInputs

Now = Callable[[], datetime]


class HintInputsAssembler:
    """Builds inputs from the discovery liquidity hint + current time."""

    def __init__(self, *, now: Now = lambda: datetime.now(UTC)) -> None:
        self._now = now

    async def build(self, token: TokenRef, *, hint_liquidity: float | None = None) -> FeatureInputs:
        liquidity = hint_liquidity or 0.0
        return FeatureInputs(
            token=token,
            now=self._now(),
            liquidity=liquidity,
            tvl=liquidity,
        )

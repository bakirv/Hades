"""History Builder — persists a snapshot every time features are computed.

Reacting to ``FeaturesComputed`` gives us a durable, timestamped record of each
token's observed state, so any historical moment can be reconstructed later
(feeding backtests, learning datasets and research). It stores facts only.
"""

from __future__ import annotations

from hades.contexts.features.domain.events import FeaturesComputed
from hades.contexts.features.domain.ports import SnapshotStore
from hades.shared_kernel.domain.events import DomainEvent
from hades.shared_kernel.events import EventBus
from hades.shared_kernel.logging import get_logger

_logger = get_logger("features.history")


class HistoryBuilder:
    """Writes a token snapshot on every ``FeaturesComputed`` event."""

    def __init__(self, store: SnapshotStore, *, schema_version: int = 1) -> None:
        self._store = store
        self._schema_version = schema_version

    def register(self, event_bus: EventBus) -> None:
        event_bus.subscribe(FeaturesComputed.__name__, self.handle)

    async def handle(self, event: DomainEvent) -> None:
        if not isinstance(event, FeaturesComputed):
            return
        features = event.features
        try:
            await self._store.save(
                features.token,
                captured_at=features.computed_at,
                state={"features": features.values, "feature_count": event.feature_count},
                schema_version=self._schema_version,
            )
        except Exception as exc:  # snapshotting is best-effort
            _logger.warning("snapshot_failed", mint=str(features.token.mint), error=str(exc))

"""Feature Engine — compose blocks into a versioned, validated feature vector.

The engine runs every :class:`FeatureBlock`, namespaces its keys, drops any
non-finite value (a corrupt feature never reaches the store), stamps the schema
version and persists the result. It then announces ``FeaturesComputed`` so the
Scoring Engine (a later phase) can react. It computes measurements only — never a
score, never a decision.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

from hades.contexts.features.application.extractors import DEFAULT_BLOCKS
from hades.contexts.features.application.extractors.base import FeatureBlock
from hades.contexts.features.domain.events import FeaturesComputed
from hades.contexts.features.domain.models import FeatureInputs, FeatureSet
from hades.contexts.features.domain.ports import FeatureStore
from hades.shared_kernel.domain.identifiers import new_id
from hades.shared_kernel.events import EventBus
from hades.shared_kernel.logging import get_logger

_logger = get_logger("features.engine")


class FeatureEngine:
    """Turns a :class:`FeatureInputs` bundle into a stored :class:`FeatureSet`."""

    def __init__(
        self,
        store: FeatureStore,
        *,
        event_bus: EventBus,
        blocks: Sequence[FeatureBlock] = DEFAULT_BLOCKS,
        schema_version: int = 1,
        on_computed: Callable[[int], None] | None = None,
    ) -> None:
        self._store = store
        self._bus = event_bus
        self._blocks = tuple(blocks)
        self._schema_version = schema_version
        self._on_computed = on_computed

    async def compute(self, inputs: FeatureInputs) -> FeatureSet:
        values: dict[str, float] = {}
        for block in self._blocks:
            try:
                block_values = block.compute(inputs)
            except Exception as exc:  # a block must not break the vector
                _logger.warning("feature_block_failed", block=block.namespace, error=str(exc))
                continue
            for key, value in block_values.items():
                if math.isfinite(value):
                    values[f"{block.namespace}.{key}"] = float(value)
                else:
                    _logger.debug("feature_dropped_non_finite", feature=f"{block.namespace}.{key}")

        feature_set = FeatureSet(
            token=inputs.token,
            computed_at=inputs.now,
            schema_version=self._schema_version,
            values=values,
        )
        await self._store.save(feature_set)
        if self._on_computed is not None:
            self._on_computed(len(values))
        await self._bus.publish(
            FeaturesComputed(
                aggregate_id=new_id(),
                token=inputs.token,
                features=feature_set,
                feature_count=len(values),
            )
        )
        return feature_set

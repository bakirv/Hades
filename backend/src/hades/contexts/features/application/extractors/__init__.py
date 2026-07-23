"""Feature extractors — one single-purpose block per feature family.

Each block turns the shared :class:`FeatureInputs` into a namespaced map of
numeric features. The Feature Engine composes them; adding a family means adding
a block and registering it — nothing else changes.
"""

from __future__ import annotations

from hades.contexts.features.application.extractors.base import FeatureBlock
from hades.contexts.features.application.extractors.basic import BasicFeatures
from hades.contexts.features.application.extractors.holders import HolderFeatures
from hades.contexts.features.application.extractors.pool import PoolFeatures
from hades.contexts.features.application.extractors.regime import MarketRegimeFeatures
from hades.contexts.features.application.extractors.technical import TechnicalFeatures
from hades.contexts.features.application.extractors.temporal import TemporalFeatures

DEFAULT_BLOCKS: tuple[FeatureBlock, ...] = (
    BasicFeatures(),
    TechnicalFeatures(),
    TemporalFeatures(),
    PoolFeatures(),
    HolderFeatures(),
    MarketRegimeFeatures(),
)

__all__ = [
    "DEFAULT_BLOCKS",
    "BasicFeatures",
    "FeatureBlock",
    "HolderFeatures",
    "MarketRegimeFeatures",
    "PoolFeatures",
    "TechnicalFeatures",
    "TemporalFeatures",
]

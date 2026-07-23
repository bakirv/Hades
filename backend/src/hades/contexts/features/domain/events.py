"""Domain events emitted by the Feature Engine."""

from __future__ import annotations

from hades.contexts.common.domain.value_objects import TokenRef
from hades.contexts.features.domain.models import FeatureSet
from hades.shared_kernel.domain.events import DomainEvent


class FeaturesComputed(DomainEvent):
    """Feature extraction finished for a token; the vector is ready to score."""

    aggregate_type: str = "token"
    token: TokenRef
    features: FeatureSet
    feature_count: int

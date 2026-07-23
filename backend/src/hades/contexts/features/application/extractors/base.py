"""Base contract for a feature block."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from hades.contexts.features.domain.models import FeatureInputs


@runtime_checkable
class FeatureBlock(Protocol):
    """Computes one namespaced family of features from the inputs bundle."""

    @property
    def namespace(self) -> str:
        """Prefix applied to every key this block emits (avoids collisions)."""
        ...

    def compute(self, inputs: FeatureInputs) -> dict[str, float]:
        """Return this block's features. Must be total (never raise)."""
        ...


def price_series(inputs: FeatureInputs) -> list[float]:
    """The historical price series (oldest -> newest), current price appended."""
    prices = [p.price for p in inputs.history]
    if inputs.price:
        prices.append(inputs.price)
    return prices

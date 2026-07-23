"""Ports defined by the Feature Engine."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from hades.contexts.common.domain.value_objects import TokenRef
from hades.contexts.features.domain.models import FeatureInputs, FeatureSet


@runtime_checkable
class SnapshotStore(Protocol):
    """Persists point-in-time token snapshots (the History Builder's store)."""

    async def save(
        self,
        token: TokenRef,
        *,
        captured_at: datetime,
        state: dict[str, Any],
        schema_version: int = 1,
    ) -> None: ...


@runtime_checkable
class FeatureInputsAssembler(Protocol):
    """Assembles the cleaned :class:`FeatureInputs` bundle for a token.

    Implementations gather current market state + rolling history (from the
    Market Engine / snapshots) into the immutable inputs the Feature Engine
    transforms. A ``hint_liquidity`` from the discovery event seeds the bundle
    before richer market data is available.
    """

    async def build(
        self, token: TokenRef, *, hint_liquidity: float | None = None
    ) -> FeatureInputs: ...


@runtime_checkable
class FeatureExtractor(Protocol):
    """Computes one group of features (composed by the engine).

    Extractors are small and single-purpose (liquidity, holders, cadence…) so
    the full feature set is the composition of many. Each returns a partial map
    that the engine merges into the final :class:`FeatureSet`.
    """

    @property
    def namespace(self) -> str:
        """Prefix applied to this extractor's feature keys (avoids collisions)."""
        ...

    async def extract(self, token: TokenRef) -> dict[str, float]: ...


@runtime_checkable
class FeatureStore(Protocol):
    """Persists and serves feature sets (training/serving parity)."""

    async def save(self, features: FeatureSet) -> None: ...

    async def latest(self, token: TokenRef) -> FeatureSet | None: ...

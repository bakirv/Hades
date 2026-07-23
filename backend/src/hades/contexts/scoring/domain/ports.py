"""Ports defined by the Scoring Engine."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from hades.contexts.features.domain.models import FeatureSet
from hades.contexts.scoring.domain.models import ProbabilisticForecast, ScoreResult


@runtime_checkable
class ScoringModel(Protocol):
    """A model that maps a feature vector to calibrated probabilities.

    Implementations wrap scikit-learn / LightGBM / XGBoost / torch models. The
    contract is deliberately narrow: features in, probabilities out. No I/O, no
    side effects, no decisions — pure and testable.
    """

    @property
    def model_id(self) -> str: ...

    async def predict(self, features: FeatureSet) -> list[ProbabilisticForecast]: ...


@runtime_checkable
class ModelRegistry(Protocol):
    """Loads/serves versioned models; enables safe rollout + rollback."""

    async def active_model(self) -> ScoringModel: ...

    async def get(self, model_id: str) -> ScoringModel: ...


@runtime_checkable
class ScoreAggregator(Protocol):
    """Combines forecasts + upstream signal scores into a composite result."""

    async def aggregate(self, *, forecasts: list[ProbabilisticForecast]) -> ScoreResult: ...

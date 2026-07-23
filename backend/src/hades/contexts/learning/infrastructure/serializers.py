"""Serialisation between the committee's value objects and JSON/ORM rows.

Kept in one place so the persistence adapters stay thin and the wire format is
consistent. Pydantic does the heavy lifting (``model_dump(mode="json")`` /
``model_validate``); these helpers just centralise the round-trips the stores use.
"""

from __future__ import annotations

from typing import Any

from hades.contexts.learning.domain.models import (
    CommitteePrediction,
    Dataset,
    DriftReport,
    FeatureImportance,
    ModelCard,
    ModelMetrics,
    ModelWeights,
    TrainingSample,
)


def prediction_to_json(prediction: CommitteePrediction) -> dict[str, Any]:
    return prediction.model_dump(mode="json")


def prediction_from_json(data: dict[str, Any]) -> CommitteePrediction:
    return CommitteePrediction.model_validate(data)


def card_to_row(card: ModelCard) -> dict[str, Any]:
    return {
        "model_id": card.model_id,
        "name": card.name,
        "version": card.version,
        "kind": card.kind,
        "status": card.status.value,
        "dataset_id": card.dataset_id,
        "feature_names": list(card.feature_names),
        "weights": {
            "primary": card.weights.model_dump(mode="json"),
            "heads": {k: v.model_dump(mode="json") for k, v in card.heads.items()},
        },
        "metrics": card.metrics.model_dump(mode="json"),
        "trained_on_samples": card.trained_on_samples,
        "notes": card.notes,
    }


def card_from_row(row: dict[str, Any]) -> ModelCard:
    from datetime import datetime

    from hades.contexts.learning.domain.models import ModelStatus

    weights_blob = row.get("weights") or {}
    primary = ModelWeights.model_validate(weights_blob.get("primary", {}))
    heads = {
        name: ModelWeights.model_validate(blob)
        for name, blob in (weights_blob.get("heads") or {}).items()
    }
    created = row.get("created_at")
    promoted = row.get("promoted_at")
    return ModelCard(
        model_id=row["model_id"],
        name=row["name"],
        version=row["version"],
        kind=row.get("kind", "logistic"),
        created_at=created if isinstance(created, datetime) else None,
        dataset_id=row.get("dataset_id"),
        feature_names=tuple(row.get("feature_names") or ()),
        weights=primary,
        heads=heads,
        metrics=ModelMetrics.model_validate(row.get("metrics") or {}),
        status=ModelStatus(row.get("status", "trained")),
        trained_on_samples=row.get("trained_on_samples", 0),
        notes=row.get("notes", ""),
        promoted_at=promoted if isinstance(promoted, datetime) else None,
    )


def dataset_to_json(dataset: Dataset) -> dict[str, Any]:
    return dataset.model_dump(mode="json")


def dataset_from_json(data: dict[str, Any]) -> Dataset:
    return Dataset.model_validate(data)


def drift_to_json(report: DriftReport) -> dict[str, Any]:
    return report.model_dump(mode="json")


def drift_from_json(data: dict[str, Any]) -> DriftReport:
    return DriftReport.model_validate(data)


def importance_to_json(importance: FeatureImportance) -> dict[str, Any]:
    return importance.model_dump(mode="json")


def importance_from_json(data: dict[str, Any]) -> FeatureImportance:
    return FeatureImportance.model_validate(data)


def sample_to_json(sample: TrainingSample) -> dict[str, Any]:
    return sample.model_dump(mode="json")


def sample_from_json(data: dict[str, Any]) -> TrainingSample:
    return TrainingSample.model_validate(data)

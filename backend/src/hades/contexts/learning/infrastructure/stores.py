"""Persistence adapters for the AI Committee — in-memory + PostgreSQL.

In-memory implementations back tests and single-process runs; the Postgres ones
back real deployments. Every store is append-only or upsert-latest in the spirit
of the rest of Hades — predictions, datasets, drift and outcomes are never
mutated after the fact, so the audit trail is complete.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence

from sqlalchemy import desc, func, select

from hades.contexts.common.domain.value_objects import TokenRef
from hades.contexts.learning.domain.models import (
    CommitteePrediction,
    Dataset,
    DriftReport,
    FeatureImportance,
    TrainingSample,
)
from hades.contexts.learning.infrastructure import serializers as ser
from hades.shared_kernel.persistence.database import Database
from hades.shared_kernel.persistence.models.learning import (
    CommitteeDatasetRecord,
    CommitteeDriftRecord,
    CommitteeFeatureImportanceRecord,
    CommitteeOutcomeRecord,
    CommitteePredictionRecord,
)

# =============================================================================
# In-memory
# =============================================================================


class InMemoryPredictionStore:
    """In-process prediction store (keeps a bounded ring of recent predictions)."""

    def __init__(self, maxlen: int = 1000) -> None:
        self._ring: deque[CommitteePrediction] = deque(maxlen=maxlen)
        self._latest: dict[str, CommitteePrediction] = {}

    async def save(self, prediction: CommitteePrediction) -> None:
        self._ring.append(prediction)
        if not prediction.shadow:
            self._latest[str(prediction.token.mint)] = prediction

    async def recent(self, limit: int = 50) -> tuple[CommitteePrediction, ...]:
        items = [p for p in reversed(self._ring) if not p.shadow]
        return tuple(items[:limit])

    async def latest_for(self, token: TokenRef) -> CommitteePrediction | None:
        return self._latest.get(str(token.mint))


class InMemoryDatasetStore:
    def __init__(self) -> None:
        self._by_id: dict[str, Dataset] = {}

    async def save(self, dataset: Dataset) -> None:
        self._by_id[dataset.dataset_id] = dataset

    async def get(self, dataset_id: str) -> Dataset | None:
        return self._by_id.get(dataset_id)


class InMemoryDriftStore:
    def __init__(self, maxlen: int = 500) -> None:
        self._ring: deque[DriftReport] = deque(maxlen=maxlen)

    async def save(self, report: DriftReport) -> None:
        self._ring.append(report)

    async def recent(self, limit: int = 50) -> tuple[DriftReport, ...]:
        return tuple(list(reversed(self._ring))[:limit])


class InMemoryFeatureImportanceStore:
    def __init__(self) -> None:
        self._latest: dict[str, FeatureImportance] = {}

    async def save(self, importance: FeatureImportance) -> None:
        self._latest[importance.model_id] = importance

    async def latest(self, model_id: str) -> FeatureImportance | None:
        return self._latest.get(model_id)


class InMemoryOutcomeStore:
    def __init__(self) -> None:
        self._samples: list[TrainingSample] = []

    async def append(self, samples: Sequence[TrainingSample]) -> None:
        self._samples.extend(samples)

    async def load(
        self, *, since_iso: str | None = None, limit: int = 100_000
    ) -> tuple[TrainingSample, ...]:
        rows = self._samples
        if since_iso is not None:
            rows = [s for s in rows if s.at.isoformat() >= since_iso]
        return tuple(rows[-limit:])

    async def count(self) -> int:
        return len(self._samples)


# =============================================================================
# PostgreSQL
# =============================================================================


class PostgresPredictionStore:
    """Durable, append-only prediction store."""

    def __init__(self, database: Database) -> None:
        self._db = database

    async def save(self, prediction: CommitteePrediction) -> None:
        async with self._db.session() as session:
            session.add(
                CommitteePredictionRecord(
                    mint=str(prediction.token.mint),
                    symbol=prediction.token.symbol,
                    at=prediction.at,
                    prob_roi_positive=prediction.meta.prob_roi_positive,
                    prob_hit_tp=prediction.meta.prob_hit_tp,
                    prob_hit_sl=prediction.meta.prob_hit_sl,
                    confidence=prediction.confidence.final,
                    regime=prediction.regime.regime.value,
                    feature_coverage=prediction.feature_coverage,
                    shadow=prediction.shadow,
                    meta_version=prediction.meta.model_version,
                    correlation_id=prediction.correlation_id,
                    prediction=ser.prediction_to_json(prediction),
                )
            )

    async def recent(self, limit: int = 50) -> tuple[CommitteePrediction, ...]:
        async with self._db.session() as session:
            rows = (
                await session.scalars(
                    select(CommitteePredictionRecord)
                    .where(CommitteePredictionRecord.shadow.is_(False))
                    .order_by(desc(CommitteePredictionRecord.at))
                    .limit(min(limit, 500))
                )
            ).all()
        return tuple(ser.prediction_from_json(r.prediction) for r in rows if r.prediction)

    async def latest_for(self, token: TokenRef) -> CommitteePrediction | None:
        async with self._db.session() as session:
            row = await session.scalar(
                select(CommitteePredictionRecord)
                .where(
                    CommitteePredictionRecord.mint == str(token.mint),
                    CommitteePredictionRecord.shadow.is_(False),
                )
                .order_by(desc(CommitteePredictionRecord.at))
                .limit(1)
            )
        return ser.prediction_from_json(row.prediction) if row and row.prediction else None


class PostgresDatasetStore:
    def __init__(self, database: Database) -> None:
        self._db = database

    async def save(self, dataset: Dataset) -> None:
        async with self._db.session() as session:
            session.add(
                CommitteeDatasetRecord(
                    dataset_id=dataset.dataset_id,
                    name=dataset.name,
                    size=dataset.size,
                    positive_rate=round(dataset.positive_rate, 4),
                    executed_count=dataset.executed_count,
                    rejected_count=dataset.rejected_count,
                    feature_names=list(dataset.feature_names),
                    samples=[ser.sample_to_json(s) for s in dataset.samples],
                    from_iso=dataset.from_iso,
                    to_iso=dataset.to_iso,
                )
            )

    async def get(self, dataset_id: str) -> Dataset | None:
        async with self._db.session() as session:
            row = await session.scalar(
                select(CommitteeDatasetRecord).where(
                    CommitteeDatasetRecord.dataset_id == dataset_id
                )
            )
        if row is None:
            return None
        return Dataset(
            dataset_id=row.dataset_id,
            name=row.name,
            samples=tuple(ser.sample_from_json(s) for s in row.samples),
            feature_names=tuple(row.feature_names),
            from_iso=row.from_iso,
            to_iso=row.to_iso,
        )


class PostgresDriftStore:
    def __init__(self, database: Database) -> None:
        self._db = database

    async def save(self, report: DriftReport) -> None:
        async with self._db.session() as session:
            session.add(
                CommitteeDriftRecord(
                    model_id=report.model_id,
                    kind=report.kind.value,
                    severity=report.severity,
                    triggered=report.triggered,
                    detail=report.detail,
                    feature_drifts=report.feature_drifts,
                    live_metrics=(
                        report.live_metrics.model_dump(mode="json") if report.live_metrics else {}
                    ),
                )
            )

    async def recent(self, limit: int = 50) -> tuple[DriftReport, ...]:
        async with self._db.session() as session:
            rows = (
                await session.scalars(
                    select(CommitteeDriftRecord)
                    .order_by(desc(CommitteeDriftRecord.created_at))
                    .limit(min(limit, 200))
                )
            ).all()
        return tuple(
            DriftReport.model_validate(
                {
                    "model_id": r.model_id,
                    "kind": r.kind,
                    "severity": r.severity,
                    "triggered": r.triggered,
                    "detail": r.detail,
                    "feature_drifts": r.feature_drifts,
                    "live_metrics": r.live_metrics or None,
                }
            )
            for r in rows
        )


class PostgresFeatureImportanceStore:
    def __init__(self, database: Database) -> None:
        self._db = database

    async def save(self, importance: FeatureImportance) -> None:
        async with self._db.session() as session:
            session.add(
                CommitteeFeatureImportanceRecord(
                    model_id=importance.model_id,
                    computed_at=importance.computed_at,
                    importances=importance.importances,
                    useless=list(importance.useless),
                    redundant=list(importance.redundant),
                    stale=list(importance.stale),
                )
            )

    async def latest(self, model_id: str) -> FeatureImportance | None:
        async with self._db.session() as session:
            row = await session.scalar(
                select(CommitteeFeatureImportanceRecord)
                .where(CommitteeFeatureImportanceRecord.model_id == model_id)
                .order_by(desc(CommitteeFeatureImportanceRecord.computed_at))
                .limit(1)
            )
        if row is None:
            return None
        return FeatureImportance(
            model_id=row.model_id,
            computed_at=row.computed_at,
            importances=row.importances,
            useless=tuple(row.useless),
            redundant=tuple(row.redundant),
            stale=tuple(row.stale),
        )


class PostgresOutcomeStore:
    def __init__(self, database: Database) -> None:
        self._db = database

    async def append(self, samples: Sequence[TrainingSample]) -> None:
        items = list(samples)
        if not items:
            return
        async with self._db.session() as session:
            session.add_all(
                CommitteeOutcomeRecord(
                    mint=s.token_mint,
                    at=s.at,
                    features=s.features,
                    label_roi_positive=s.label_roi_positive,
                    label_hit_tp=s.label_hit_tp,
                    label_hit_sl=s.label_hit_sl,
                    realized_roi=s.realized_roi,
                    was_executed=s.was_executed,
                    was_rejected=s.was_rejected,
                    weight=s.weight,
                )
                for s in items
            )

    async def load(
        self, *, since_iso: str | None = None, limit: int = 100_000
    ) -> tuple[TrainingSample, ...]:
        async with self._db.session() as session:
            rows = (
                await session.scalars(
                    select(CommitteeOutcomeRecord).order_by(CommitteeOutcomeRecord.at).limit(limit)
                )
            ).all()
        return tuple(
            TrainingSample(
                token_mint=r.mint,
                at=r.at,
                features=r.features,
                label_roi_positive=r.label_roi_positive,
                label_hit_tp=r.label_hit_tp,
                label_hit_sl=r.label_hit_sl,
                realized_roi=r.realized_roi,
                was_executed=r.was_executed,
                was_rejected=r.was_rejected,
                weight=r.weight,
            )
            for r in rows
        )

    async def count(self) -> int:
        async with self._db.session() as session:
            total = await session.scalar(select(func.count()).select_from(CommitteeOutcomeRecord))
        return int(total or 0)

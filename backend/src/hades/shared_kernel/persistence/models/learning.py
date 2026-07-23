"""AI Committee tables — the brain's auditable, versioned memory.

These persist what the Learning context produces and must never lose:

* ``committee_predictions`` — every fused verdict (the three probabilities, the
  confidence decomposition, the regime, the opinions and the explanation), stored
  verbatim so any later decision is fully traceable. Append-only.
* ``committee_models`` — the append-only Model Registry: one immutable row per
  ``(name, version)`` with its transparent weights, features, dataset and metrics.
  Never overwritten; promotion is a status transition.
* ``committee_datasets`` — assembled training sets, for reproducibility.
* ``committee_feature_importance`` — the continuously-computed importance snapshots.
* ``committee_drift`` — detected model degradation over time.
* ``committee_outcomes`` — the labelled outcome ledger (executed *and* rejected),
  the raw material the Dataset Builder learns from.

All follow the platform rule (UUIDv7 pk + timestamps via mixins). Nothing here
represents a trade decision — only probabilities, models and evidence.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hades.shared_kernel.persistence.database import Base
from hades.shared_kernel.persistence.models._mixins import TimestampMixin, UUIDPrimaryKeyMixin


class CommitteePredictionRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One complete, auditable committee verdict for a token."""

    __tablename__ = "committee_predictions"

    mint: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(64))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    prob_roi_positive: Mapped[float] = mapped_column(Float, index=True, nullable=False)
    prob_hit_tp: Mapped[float] = mapped_column(Float, nullable=False)
    prob_hit_sl: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, index=True, nullable=False)
    regime: Mapped[str] = mapped_column(String(24), index=True, default="unknown", nullable=False)
    feature_coverage: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    shadow: Mapped[bool] = mapped_column(Boolean, index=True, default=False, nullable=False)
    meta_version: Mapped[str | None] = mapped_column(String(50))
    correlation_id: Mapped[str | None] = mapped_column(String(64), index=True)
    # The full CommitteePrediction, serialised (opinions, confidence, explanation).
    prediction: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class CommitteeModelRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A registry entry: one immutable, versioned, transparent model."""

    __tablename__ = "committee_models"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_committee_models_name_version"),)

    model_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), default="logistic", nullable=False)
    status: Mapped[str] = mapped_column(String(24), index=True, default="trained", nullable=False)
    dataset_id: Mapped[str | None] = mapped_column(String(64), index=True)
    feature_names: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    weights: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    trained_on_samples: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CommitteeDatasetRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An assembled training set, kept for reproducibility."""

    __tablename__ = "committee_datasets"

    dataset_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    positive_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    executed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    feature_names: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    samples: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    from_iso: Mapped[str | None] = mapped_column(String(40))
    to_iso: Mapped[str | None] = mapped_column(String(40))


class CommitteeFeatureImportanceRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A continuously-computed feature-importance snapshot for a model."""

    __tablename__ = "committee_feature_importance"

    model_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    importances: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    useless: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    redundant: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    stale: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)


class CommitteeDriftRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A detected drift event for an active model."""

    __tablename__ = "committee_drift"

    model_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), index=True, default="none", nullable=False)
    severity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    triggered: Mapped[bool] = mapped_column(Boolean, index=True, default=False, nullable=False)
    detail: Mapped[str] = mapped_column(Text, default="", nullable=False)
    feature_drifts: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    live_metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class CommitteeOutcomeRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One labelled outcome the brain learns from (executed or rejected)."""

    __tablename__ = "committee_outcomes"

    mint: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    features: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    label_roi_positive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    label_hit_tp: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    label_hit_sl: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    realized_roi: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    was_executed: Mapped[bool] = mapped_column(Boolean, index=True, default=True, nullable=False)
    was_rejected: Mapped[bool] = mapped_column(Boolean, index=True, default=False, nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

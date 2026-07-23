"""Strategy catalogue, its versioned genomes, and trained ML models.

Nothing here decides trades in Phase 2 — these are the tables the Scoring /
Learning / Research contexts will write to in later phases. They are defined now
so the schema is complete and stable from the start.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hades.shared_kernel.persistence.database import Base
from hades.shared_kernel.persistence.models._mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Model(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A trained/evaluated ML model artifact in the registry.

    ``status`` follows the promotion lifecycle: trained → shadow → promoted, or
    rejected. Promotion is always human-gated (never automatic).
    """

    __tablename__ = "models"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_models_name_version"),)

    name: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    kind: Mapped[str | None] = mapped_column(String(50), index=True)
    framework: Mapped[str | None] = mapped_column(String(50))
    artifact_path: Mapped[str | None] = mapped_column(String(500))
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="trained", index=True, nullable=False)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Strategy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A named trading strategy. Concrete rules live in its versions."""

    __tablename__ = "strategies"

    name: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str | None] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(30), default="inactive", index=True, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    versions: Mapped[list[StrategyVersion]] = relationship(
        "StrategyVersion", back_populates="strategy", lazy="raise", cascade="all, delete-orphan"
    )


class StrategyVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An immutable, versioned snapshot of a strategy's genome/config."""

    __tablename__ = "strategy_versions"
    __table_args__ = (
        UniqueConstraint("strategy_id", "version", name="uq_strategy_versions_strategy_version"),
    )

    strategy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    genome: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    model_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("models.id", ondelete="SET NULL"), index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    strategy: Mapped[Strategy] = relationship("Strategy", back_populates="versions", lazy="raise")

"""Scoring output records.

A ``Signal`` is what the Scoring Engine produces: calibrated probabilities,
confidence and a composite score with an explanation — **never a buy/sell
decision** (that authority belongs to the Risk Manager). Kept as an auditable
row so every later decision can be traced back to the score that informed it.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hades.shared_kernel.persistence.database import Base
from hades.shared_kernel.persistence.models._mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Signal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One fused score for a token at a moment (explainable, versioned)."""

    __tablename__ = "signals"

    token_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tokens.id", ondelete="CASCADE"), index=True, nullable=False
    )
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("strategies.id", ondelete="SET NULL"), index=True
    )
    model_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("models.id", ondelete="SET NULL"), index=True
    )
    security_score: Mapped[float | None] = mapped_column(Float)
    wallet_score: Mapped[float | None] = mapped_column(Float)
    final_score: Mapped[float | None] = mapped_column(Float, index=True)
    probability: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
    model_version: Mapped[str | None] = mapped_column(String(50))
    correlation_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    explanation: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

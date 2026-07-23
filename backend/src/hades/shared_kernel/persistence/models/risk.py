"""Risk Manager persistence - the decision audit trail and durable control state.

``risk_decisions`` is the append-only record of every approval/rejection with its
full explanation (so any committed trade traces back to the exact reasoning).
``risk_control_state`` holds the single, latest defence-layer posture (Kill Switch
level, Circuit Breaker, Emergency Mode) so a halt survives a restart. Both carry
the full value object as JSONB alongside the queryable columns.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hades.shared_kernel.persistence.database import Base
from hades.shared_kernel.persistence.models._mixins import TimestampMixin, UUIDPrimaryKeyMixin

_AMOUNT = Numeric(38, 18)


class RiskDecisionRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One risk verdict - approve or reject - with its full, auditable reasoning."""

    __tablename__ = "risk_decisions"

    mint: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(64))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    decision: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    reject_reason: Mapped[str | None] = mapped_column(String(40), index=True)
    conviction: Mapped[float | None] = mapped_column(Numeric(9, 6))
    risk_amount_usd: Mapped[Decimal | None] = mapped_column(_AMOUNT)
    notional_usd: Mapped[Decimal | None] = mapped_column(_AMOUNT)
    headline: Mapped[str | None] = mapped_column(Text)
    strategy: Mapped[str | None] = mapped_column(String(40), index=True)
    kill_switch_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    circuit_breaker_open: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(64), index=True)
    assessment: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class RiskControlStateRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The latest defence-layer posture - one logical row (``key`` is unique)."""

    __tablename__ = "risk_control_state"

    key: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    kill_switch_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    circuit_breaker_open: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    emergency_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    state: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

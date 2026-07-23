"""Position book of record and the trade ledger.

``trades`` is the canonical, mode-agnostic execution ledger. ``paper_trades``
and ``live_trades`` hold the mode-specific detail of each trade (1:1), so the
paper↔live seam is visible in the schema without duplicating the ledger. All
monetary/quantity columns use ``Numeric`` (never float) to avoid rounding error.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hades.shared_kernel.persistence.database import Base
from hades.shared_kernel.persistence.models._mixins import TimestampMixin, UUIDPrimaryKeyMixin

# 38 digits, 18 fractional — comfortably covers SPL token amounts and USD values.
_AMOUNT = Numeric(38, 18)


class Position(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A tracked position in one token — the consistency boundary for a trade."""

    __tablename__ = "positions"

    token_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tokens.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("strategies.id", ondelete="SET NULL"), index=True
    )
    mode: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(_AMOUNT, default=Decimal(0), nullable=False)
    entry_price: Mapped[Decimal | None] = mapped_column(_AMOUNT)
    mark_price: Mapped[Decimal | None] = mapped_column(_AMOUNT)
    stop_price: Mapped[Decimal | None] = mapped_column(_AMOUNT)
    realized_pnl: Mapped[Decimal | None] = mapped_column(_AMOUNT)
    unrealized_pnl: Mapped[Decimal | None] = mapped_column(_AMOUNT)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    trades: Mapped[list[Trade]] = relationship("Trade", back_populates="position", lazy="raise")


class Trade(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single execution (buy or sell) in the mode-agnostic ledger."""

    __tablename__ = "trades"

    position_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("positions.id", ondelete="SET NULL"), index=True
    )
    token_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tokens.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("strategies.id", ondelete="SET NULL"), index=True
    )
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    mode: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="submitted", index=True, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(_AMOUNT, nullable=False)
    price: Mapped[Decimal | None] = mapped_column(_AMOUNT)
    notional_usd: Mapped[Decimal | None] = mapped_column(_AMOUNT)
    fee_usd: Mapped[Decimal | None] = mapped_column(_AMOUNT)
    slippage_bps: Mapped[int | None] = mapped_column(Integer)
    correlation_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(Text)

    position: Mapped[Position | None] = relationship(
        "Position", back_populates="trades", lazy="raise"
    )
    paper_detail: Mapped[PaperTrade | None] = relationship(
        "PaperTrade",
        back_populates="trade",
        lazy="raise",
        uselist=False,
        cascade="all, delete-orphan",
    )
    live_detail: Mapped[LiveTrade | None] = relationship(
        "LiveTrade",
        back_populates="trade",
        lazy="raise",
        uselist=False,
        cascade="all, delete-orphan",
    )


class PaperTrade(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Mode-specific detail for a simulated (paper) trade."""

    __tablename__ = "paper_trades"

    trade_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("trades.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    simulated_latency_ms: Mapped[int | None] = mapped_column(Integer)
    simulated_slippage_bps: Mapped[int | None] = mapped_column(Integer)
    simulated_price: Mapped[Decimal | None] = mapped_column(_AMOUNT)
    notes: Mapped[str | None] = mapped_column(Text)

    trade: Mapped[Trade] = relationship("Trade", back_populates="paper_detail", lazy="raise")


class LiveTrade(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Mode-specific detail for a real on-chain (live) trade."""

    __tablename__ = "live_trades"

    trade_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("trades.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    tx_signature: Mapped[str | None] = mapped_column(String(120), unique=True, index=True)
    block_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    priority_fee_microlamports: Mapped[int | None] = mapped_column(Integer)
    confirmation_status: Mapped[str | None] = mapped_column(String(20))
    rpc_url: Mapped[str | None] = mapped_column(String(300))

    trade: Mapped[Trade] = relationship("Trade", back_populates="live_detail", lazy="raise")

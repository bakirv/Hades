"""Token & Wallet reference tables — the identities everything else keys on."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hades.shared_kernel.persistence.database import Base
from hades.shared_kernel.persistence.models._mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Wallet(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A Solana wallet (deployer, holder, liquidity provider, smart money)."""

    __tablename__ = "wallets"

    address: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    label: Mapped[str | None] = mapped_column(String(200))
    is_deployer: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_smart_money: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_blacklisted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reputation_score: Mapped[float | None] = mapped_column(Float)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class Token(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An SPL token discovered by the Scanner. ``mint`` is its canonical id."""

    __tablename__ = "tokens"

    mint: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(64), index=True)
    name: Mapped[str | None] = mapped_column(String(200))
    decimals: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str | None] = mapped_column(String(50), index=True)
    deployer_wallet_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("wallets.id", ondelete="SET NULL"), index=True
    )
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    is_blacklisted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_whitelisted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    deployer: Mapped[Wallet | None] = relationship("Wallet", lazy="raise")

"""Wallet Intelligence tables — the permanent on-chain knowledge base.

These persist what the intelligence context *learns and never forgets*:

* ``wallet_profiles`` — the current profile for every wallet ever observed (one
  row per wallet, upserted to its latest version).
* ``wallet_history`` — an append-only version log: every past profile snapshot,
  kept forever so a wallet's reputation can be replayed through time.
* ``wallet_timeline`` — the append-only per-wallet event timeline.
* ``wallet_relationships`` — the directed funding / co-holding graph.
* ``intel_clusters`` — detected coordinated-wallet entities.
* ``wallet_knowledge`` — an append-only ledger of every intelligence event.

Nothing here is ever deleted. All follow the platform rule (UUIDv7 pk + timestamps
via mixins).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hades.shared_kernel.persistence.database import Base
from hades.shared_kernel.persistence.models._mixins import TimestampMixin, UUIDPrimaryKeyMixin


class WalletProfileRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The current accumulated profile for one wallet."""

    __tablename__ = "wallet_profiles"

    address: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    observations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_traded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    launches: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rugs_participated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    successes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    dexes: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    roles: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    avg_pct_supply: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    reputation: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    behavior: Mapped[str] = mapped_column(String(24), default="unknown", nullable=False)
    behavior_confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    money_class: Mapped[str] = mapped_column(
        String(16), index=True, default="neutral", nullable=False
    )
    smart_money_score: Mapped[float] = mapped_column(
        Float, index=True, default=50.0, nullable=False
    )
    influence: Mapped[float] = mapped_column(Float, index=True, default=0.0, nullable=False)
    funding: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    cluster_id: Mapped[str | None] = mapped_column(String(32), index=True)
    score: Mapped[float] = mapped_column(Float, index=True, default=50.0, nullable=False)
    band: Mapped[str] = mapped_column(String(16), index=True, default="neutral", nullable=False)
    explanation: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class WalletHistoryRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An append-only snapshot of a wallet profile at a point in time."""

    __tablename__ = "wallet_history"
    __table_args__ = (UniqueConstraint("address", "version", name="uq_wallet_history_version"),)

    address: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    band: Mapped[str] = mapped_column(String(16), nullable=False)
    reputation: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )


class WalletTimelineRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One dated event in a wallet's life (append-only)."""

    __tablename__ = "wallet_timeline"

    address: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    mint: Mapped[str | None] = mapped_column(String(64), index=True)
    detail: Mapped[str] = mapped_column(Text, default="", nullable=False)


class WalletRelationshipRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A directed edge in the wallet graph (funding / co-holding / clustering)."""

    __tablename__ = "wallet_relationships"
    __table_args__ = (UniqueConstraint("source", "target", "kind", name="uq_wallet_relationship"),)

    source: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    target: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    observations: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class IntelClusterRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A coordinated-wallet cluster detected by the intelligence engine."""

    __tablename__ = "intel_clusters"

    cluster_id: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    funder: Mapped[str | None] = mapped_column(String(64), index=True)
    member_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reason: Mapped[str] = mapped_column(String(32), default="common_funder", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    pct_supply: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    members: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )


class WalletKnowledgeRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An append-only ledger entry of something the platform learned."""

    __tablename__ = "wallet_knowledge"

    address: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)

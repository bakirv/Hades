"""Security Engine tables — assessments, reputation lists, dev history, clusters.

These persist what the Security Engine *learns and decides*:

* ``security_assessments`` — the full verdict for every token, approved **and**
  rejected. Rejected tokens are the richest training data, so nothing is thrown
  away (Research requirement).
* ``blacklist_entries`` / ``whitelist_entries`` — append-only reputation lists.
  Rows are deactivated, never deleted, so we can always explain a past block.
* ``developer_reputation`` — the deployer track record accumulated over time.
* ``wallet_clusters`` — coordinated-wallet findings per token.

All follow the platform rule (UUIDv7 pk + timestamps via mixins).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hades.shared_kernel.persistence.database import Base
from hades.shared_kernel.persistence.models._mixins import TimestampMixin, UUIDPrimaryKeyMixin


class SecurityAssessmentRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One security verdict for a token (kept for audit and research)."""

    __tablename__ = "security_assessments"

    token_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tokens.id", ondelete="CASCADE"), index=True
    )
    mint: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    decision: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    approved: Mapped[bool] = mapped_column(Boolean, index=True, nullable=False)
    vetoed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    score: Mapped[float] = mapped_column(Float, index=True, nullable=False)
    sub_scores: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    flags: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    positives: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    explanation: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    facts: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    analyzed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    duration_ms: Mapped[float | None] = mapped_column(Float)


class BlacklistEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An append-only malicious-subject record (wallet/token/pool/deployer…)."""

    __tablename__ = "blacklist_entries"

    kind: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    value: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="engine", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)


class WhitelistEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An append-only trusted-subject record (proven wallet/dev/project…)."""

    __tablename__ = "whitelist_entries"

    kind: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    value: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)


class DeveloperReputation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A deployer's accumulated track record as Hades has observed it."""

    __tablename__ = "developer_reputation"

    deployer: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    tokens_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rugs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    survived: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    successes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_lifetime_hours: Mapped[float | None] = mapped_column(Float)
    avg_roi: Mapped[float | None] = mapped_column(Float)
    is_known_scammer: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class WalletClusterRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A coordinated-wallet cluster detected behind a token's holders."""

    __tablename__ = "wallet_clusters"

    mint: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    funder: Mapped[str | None] = mapped_column(String(64), index=True)
    member_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pct_supply: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    members: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )

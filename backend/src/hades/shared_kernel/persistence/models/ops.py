"""Operational tables: notifications, health checks, risk events, audit, config.

``system_configuration`` is the DB-side authority for runtime-mutable settings
(most notably the trading mode) that must stay consistent across env, DB, API,
dashboard and the notification service. ``config_snapshots`` is the append-only,
versioned history of the non-secret configuration posture (Phase 10 Configuration
Manager) — export/diff/drift build on it.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hades.shared_kernel.persistence.database import Base
from hades.shared_kernel.persistence.models._mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Notification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An outbound notification and its delivery status (Discord only, for now).

    Persisted by the Notification Service — the single component allowed to send.
    No other module ever talks to Discord directly.
    """

    __tablename__ = "notifications"

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    channel: Mapped[str] = mapped_column(String(30), default="discord", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True, nullable=False)
    dedup_key: Mapped[str | None] = mapped_column(String(200), index=True)
    tags: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)


class HealthCheck(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A recorded probe result from the Watchdog / Health Monitor."""

    __tablename__ = "health_checks"

    component: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[float | None] = mapped_column(Float)
    instance_id: Mapped[str | None] = mapped_column(String(80), index=True)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )


class RiskEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A risk-relevant occurrence (kill switch, limit breach, mode change…)."""

    __tablename__ = "risk_events"

    kind: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    mode: Mapped[str | None] = mapped_column(String(10), index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )


class AuditLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An append-only audit trail of consequential actions (who/what/when)."""

    __tablename__ = "audit_log"

    actor: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    action: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(80), index=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    source_ip: Mapped[str | None] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )


class SystemConfiguration(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A runtime-mutable configuration value, keyed by name (DB authority)."""

    __tablename__ = "system_configuration"

    key: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    value_type: Mapped[str] = mapped_column(String(30), default="json", nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String(120))


class ConfigSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An append-only, versioned snapshot of the non-secret config posture.

    Written by the Configuration Manager so configuration can be versioned,
    diffed, exported and drift-checked over the platform's life. Secrets are
    redacted before a payload ever reaches this table. ``checksum`` is the SHA-256
    of the canonical payload, so identical snapshots are detectable and integrity
    is verifiable.
    """

    __tablename__ = "config_snapshots"

    version: Mapped[int] = mapped_column(index=True, unique=True, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    created_by: Mapped[str] = mapped_column(String(120), default="system", nullable=False)
    note: Mapped[str | None] = mapped_column(Text)

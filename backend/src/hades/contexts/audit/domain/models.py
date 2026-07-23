"""Audit value objects — an immutable entry and a query specification.

An :class:`AuditEntry` mirrors one row of the append-only ``audit_log`` table but
lives in the domain (transport/ORM-agnostic). ``before``/``after`` are free-form
JSON snapshots so any change — a promoted model, an edited threshold, a mode
switch — decomposes into what it was and what it became.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import Field

from hades.shared_kernel.domain.base import ValueObject


class AuditEntry(ValueObject):
    """One consequential action, recorded for all time.

    ``entity_id`` is an optional stable identifier (a UUID string when the action
    targets an aggregate; ``None`` for platform-wide actions like a config edit,
    whose subject is carried in ``action``/``entity_type`` instead).
    """

    actor: str = "system"
    action: str
    entity_type: str | None = None
    entity_id: str | None = None
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    source_ip: str | None = None
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AuditQuery(ValueObject):
    """Filter for reading the trail. All fields optional; results newest-first."""

    actor: str | None = None
    action: str | None = None
    entity_type: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    limit: int = 100
    offset: int = 0

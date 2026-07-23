"""Ports the Audit context defines.

- :class:`AuditTrail` — what platform services depend on to *record* an action.
  The recorder implements it; callers never touch the store or the ORM.
- :class:`AuditStore` — the persistence port (a Postgres adapter and an
  in-memory adapter implement it).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from hades.contexts.audit.domain.models import AuditEntry, AuditQuery


@runtime_checkable
class AuditTrail(Protocol):
    """The sanctioned way to record a consequential action."""

    async def record(self, entry: AuditEntry) -> None:
        """Append one entry. Implementations must never raise to the caller —
        a failed audit is logged, but it must not break the audited action."""
        ...


@runtime_checkable
class AuditStore(Protocol):
    """Append-only persistence for audit entries."""

    async def append(self, entry: AuditEntry) -> None: ...

    async def query(self, spec: AuditQuery) -> list[AuditEntry]: ...

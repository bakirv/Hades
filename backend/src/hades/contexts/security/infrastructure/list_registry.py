"""Reputation-list registry adapters — PostgreSQL + in-memory.

Black/white lists are **append-only**: adding an entry inserts a row, and a
lookup asks whether any *active* row exists for a subject. History is never
destroyed, so we can always reconstruct why a subject was trusted or blocked.
"""

from __future__ import annotations

from sqlalchemy import select

from hades.shared_kernel.persistence.database import Database
from hades.shared_kernel.persistence.models import BlacklistEntry, WhitelistEntry


class PostgresListRegistry:
    """PostgreSQL-backed append-only black/white lists."""

    def __init__(self, database: Database) -> None:
        self._db = database

    async def is_blacklisted(self, kind: str, value: str) -> bool:
        async with self._db.session() as session:
            row = await session.scalar(
                select(BlacklistEntry.id)
                .where(
                    BlacklistEntry.kind == kind,
                    BlacklistEntry.value == value,
                    BlacklistEntry.active.is_(True),
                )
                .limit(1)
            )
            return row is not None

    async def is_whitelisted(self, kind: str, value: str) -> bool:
        async with self._db.session() as session:
            row = await session.scalar(
                select(WhitelistEntry.id)
                .where(
                    WhitelistEntry.kind == kind,
                    WhitelistEntry.value == value,
                    WhitelistEntry.active.is_(True),
                )
                .limit(1)
            )
            return row is not None

    async def add_blacklist(
        self, kind: str, value: str, *, reason: str, source: str = "engine"
    ) -> None:
        async with self._db.session() as session:
            session.add(BlacklistEntry(kind=kind, value=value, reason=reason, source=source))

    async def add_whitelist(
        self, kind: str, value: str, *, reason: str, source: str = "manual"
    ) -> None:
        async with self._db.session() as session:
            session.add(WhitelistEntry(kind=kind, value=value, reason=reason, source=source))


class InMemoryListRegistry:
    """In-process append-only lists for tests and single-process runs."""

    def __init__(self) -> None:
        self.blacklist: list[tuple[str, str, str, str]] = []
        self.whitelist: list[tuple[str, str, str, str]] = []

    async def is_blacklisted(self, kind: str, value: str) -> bool:
        return any(k == kind and v == value for k, v, _, _ in self.blacklist)

    async def is_whitelisted(self, kind: str, value: str) -> bool:
        return any(k == kind and v == value for k, v, _, _ in self.whitelist)

    async def add_blacklist(
        self, kind: str, value: str, *, reason: str, source: str = "engine"
    ) -> None:
        self.blacklist.append((kind, value, reason, source))

    async def add_whitelist(
        self, kind: str, value: str, *, reason: str, source: str = "manual"
    ) -> None:
        self.whitelist.append((kind, value, reason, source))

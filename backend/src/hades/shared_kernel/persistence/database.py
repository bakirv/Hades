"""Async SQLAlchemy engine + session lifecycle.

A single :class:`Database` owns the engine and hands out sessions. The write
model (event store + operational tables) lives in PostgreSQL. Read models may
later live in ClickHouse; those adapters live in their own contexts and do not
touch this class.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from hades.shared_kernel.logging import get_logger

_logger = get_logger("persistence.database")

# Deterministic constraint/index names so Alembic migrations are stable and
# reviewable across the whole schema (no auto-generated random names).
_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base for all ORM-mapped persistence models."""

    metadata = MetaData(naming_convention=_NAMING_CONVENTION)


class Database:
    """Owns the async engine and session factory."""

    def __init__(self, dsn: str, *, pool_size: int = 10, max_overflow: int = 20) -> None:
        self._engine: AsyncEngine = create_async_engine(
            dsn,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=True,
            future=True,
        )
        self._session_factory = async_sessionmaker(
            self._engine, expire_on_commit=False, class_=AsyncSession
        )

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield a session, committing on success and rolling back on error."""
        session = self._session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def dispose(self) -> None:
        await self._engine.dispose()
        _logger.info("database_disposed")

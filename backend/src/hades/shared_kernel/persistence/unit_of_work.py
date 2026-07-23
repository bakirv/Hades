"""Unit of Work contract.

A Unit of Work groups all changes of one command into a single atomic
transaction: aggregates are saved and their domain events are appended to the
event store together, then published to the bus only after the commit succeeds.
This guarantees we never publish an event for a change that was rolled back.

The port is defined here; concrete implementations (SQLAlchemy-backed) live in
``infrastructure`` so the application layer depends only on this abstraction.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from types import TracebackType


class UnitOfWork(ABC):
    """Transactional boundary. Use as an async context manager.

    Typical handler usage::

        async with uow:
            aggregate = await uow.positions.get(position_id)
            aggregate.close(reason)
            await uow.positions.save(aggregate)
            await uow.commit()   # appends events, then publishes them
    """

    async def __aenter__(self) -> UnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            await self.rollback()

    @abstractmethod
    async def commit(self) -> None:
        """Persist changes + events atomically, then publish events."""
        raise NotImplementedError

    @abstractmethod
    async def rollback(self) -> None:
        """Discard all changes made within this unit of work."""
        raise NotImplementedError

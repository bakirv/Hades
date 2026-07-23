"""Query side of CQRS.

A :class:`Query` is an immutable read request. Handlers read from projections /
read models only — they must never mutate state or emit events.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict


class Query(BaseModel):
    """Immutable read request (``GetOpenPositionsQuery``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")


TQuery = TypeVar("TQuery", bound=Query)
TResult = TypeVar("TResult")


class QueryHandler(ABC, Generic[TQuery, TResult]):
    """Handles exactly one query type. Read-only."""

    @abstractmethod
    async def handle(self, query: TQuery) -> TResult:
        raise NotImplementedError

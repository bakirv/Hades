"""Command side of CQRS.

A :class:`Command` is an immutable intent to change state ("open a position").
Exactly one :class:`CommandHandler` handles each command type. Handlers load an
aggregate, invoke domain behaviour, persist via the unit of work, and let the
resulting events flow to the bus.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict


class Command(BaseModel):
    """Immutable write intent. Named imperatively (``OpenPositionCommand``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")


TCommand = TypeVar("TCommand", bound=Command)
TResult = TypeVar("TResult")


class CommandHandler(ABC, Generic[TCommand, TResult]):
    """Handles exactly one command type."""

    @abstractmethod
    async def handle(self, command: TCommand) -> TResult:
        """Execute the command and return its result (often an id or nothing)."""
        raise NotImplementedError

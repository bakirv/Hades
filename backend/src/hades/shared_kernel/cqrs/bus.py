"""In-process command and query dispatchers.

Handlers register against a concrete command/query *type*. The bus looks up the
single handler and invokes it. This indirection lets the API layer stay ignorant
of application wiring and makes cross-cutting concerns (logging, metrics,
transactions, validation) attachable in one place later as middleware.
"""

from __future__ import annotations

from typing import Any

from hades.shared_kernel.cqrs.command import Command, CommandHandler
from hades.shared_kernel.cqrs.query import Query, QueryHandler
from hades.shared_kernel.errors import ConfigurationError
from hades.shared_kernel.logging import get_logger

_logger = get_logger("cqrs.bus")


class CommandBus:
    """Routes a command instance to its registered handler."""

    def __init__(self) -> None:
        self._handlers: dict[type[Command], CommandHandler[Any, Any]] = {}

    def register(self, command_type: type[Command], handler: CommandHandler[Any, Any]) -> None:
        if command_type in self._handlers:
            raise ConfigurationError(f"duplicate command handler for {command_type.__name__}")
        self._handlers[command_type] = handler

    async def dispatch(self, command: Command) -> Any:
        handler = self._handlers.get(type(command))
        if handler is None:
            raise ConfigurationError(f"no handler for command {type(command).__name__}")
        _logger.debug("command_dispatch", command=type(command).__name__)
        return await handler.handle(command)


class QueryBus:
    """Routes a query instance to its registered handler."""

    def __init__(self) -> None:
        self._handlers: dict[type[Query], QueryHandler[Any, Any]] = {}

    def register(self, query_type: type[Query], handler: QueryHandler[Any, Any]) -> None:
        if query_type in self._handlers:
            raise ConfigurationError(f"duplicate query handler for {query_type.__name__}")
        self._handlers[query_type] = handler

    async def dispatch(self, query: Query) -> Any:
        handler = self._handlers.get(type(query))
        if handler is None:
            raise ConfigurationError(f"no handler for query {type(query).__name__}")
        return await handler.handle(query)

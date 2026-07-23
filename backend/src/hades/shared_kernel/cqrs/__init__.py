"""CQRS: separate the write side (commands) from the read side (queries).

Commands mutate state and emit events; they run against the operational store
(PostgreSQL). Queries never mutate; they read from projections / read models
(PostgreSQL views today, ClickHouse tomorrow). Keeping them apart means heavy
analytical reads never contend with the trading write path.
"""

from hades.shared_kernel.cqrs.bus import CommandBus, QueryBus
from hades.shared_kernel.cqrs.command import Command, CommandHandler
from hades.shared_kernel.cqrs.query import Query, QueryHandler

__all__ = [
    "Command",
    "CommandBus",
    "CommandHandler",
    "Query",
    "QueryBus",
    "QueryHandler",
]

"""Event bus — the asynchronous backbone of the platform.

Contexts never call each other directly. They publish domain events; interested
contexts subscribe. This keeps modules decoupled and independently deployable:
today the bus is in-process, tomorrow the same interface is backed by Redis
Streams (or Kafka) so a context can move to its own container without any caller
changing.

The port is :class:`EventBus`. Two implementations ship:
- :class:`InMemoryEventBus` for tests and single-process runs.
- A Redis-backed bus (see ``infrastructure``) selected by ``EVENT_BUS_TRANSPORT``.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable

from hades.shared_kernel.domain.events import DomainEvent
from hades.shared_kernel.logging import get_logger

# A handler reacts to one event. Handlers must be idempotent: the bus guarantees
# at-least-once delivery, never exactly-once.
EventHandler = Callable[[DomainEvent], Awaitable[None]]

_logger = get_logger("events.bus")


@runtime_checkable
class EventBus(Protocol):
    """Publish/subscribe contract. Route on ``event_type`` (the class name)."""

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Register ``handler`` for events whose ``event_type`` matches."""
        ...

    async def publish(self, event: DomainEvent) -> None:
        """Publish a single event to all matching subscribers."""
        ...

    async def publish_many(self, events: list[DomainEvent]) -> None:
        """Publish a batch, preserving order."""
        ...


class InMemoryEventBus:
    """Simple asyncio in-process bus. Delivers to handlers concurrently.

    Handler exceptions are logged and swallowed so one failing subscriber never
    blocks others — reliability guarantees belong to the durable (Redis) bus.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)
        _logger.debug("handler_subscribed", event_type=event_type)

    async def publish(self, event: DomainEvent) -> None:
        handlers = self._handlers.get(event.event_type, [])
        if not handlers:
            return
        results = await asyncio.gather(
            *(self._safe_invoke(h, event) for h in handlers),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                _logger.error(
                    "event_handler_failed",
                    event_type=event.event_type,
                    error=str(result),
                )

    async def publish_many(self, events: list[DomainEvent]) -> None:
        for event in events:
            await self.publish(event)

    @staticmethod
    async def _safe_invoke(handler: EventHandler, event: DomainEvent) -> None:
        await handler(event)

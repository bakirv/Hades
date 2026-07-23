"""Redis Streams event-bus transport.

Selected when ``EVENT_BUS_TRANSPORT=redis``. It gives Hades a durable,
multi-service event backbone with the same :class:`EventBus` interface as the
in-memory bus, so no publisher or subscriber changes when a context moves to its
own container.

Semantics:
- **Publish** ``XADD`` s the event envelope to one stream.
- **Consume** uses a per-service **consumer group** (so every service sees every
  event — each group gets its own copy) and a consumer named after the instance.
- Delivery is **at-least-once**; handlers must be idempotent (same contract as
  the in-memory bus). Messages are ``XACK`` ed only after handlers run.

The consumer loop runs via :meth:`run` and is launched by the background process
that owns the bus (worker / engine / watchdog / notification / scheduler).
"""

from __future__ import annotations

import asyncio
from typing import Any

import orjson

from hades.shared_kernel.cache.redis_provider import RedisProvider
from hades.shared_kernel.domain.events import DomainEvent
from hades.shared_kernel.events.bus import EventHandler
from hades.shared_kernel.events.registry import EventRegistry
from hades.shared_kernel.logging import get_logger

_logger = get_logger("events.redis_bus")


class RedisEventBus:
    """Durable event bus over a single Redis Stream + per-service group."""

    def __init__(
        self,
        provider: RedisProvider,
        registry: EventRegistry,
        *,
        stream_prefix: str = "hades.events",
        group: str = "default",
        consumer: str = "consumer-1",
        block_ms: int = 2000,
        batch: int = 50,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._stream = f"{stream_prefix}:stream"
        self._group = group
        self._consumer = consumer
        self._block_ms = block_ms
        self._batch = batch
        self._handlers: dict[str, list[EventHandler]] = {}
        self._stop = asyncio.Event()
        self._group_ready = False

    # --- EventBus interface ---------------------------------------------------
    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)
        _logger.debug("handler_subscribed", event_type=event_type, group=self._group)

    async def publish(self, event: DomainEvent) -> None:
        envelope = event.to_envelope()
        await self._provider.client().xadd(
            self._stream,
            {"type": event.event_type, "data": orjson.dumps(envelope).decode()},
        )

    async def publish_many(self, events: list[DomainEvent]) -> None:
        for event in events:
            await self.publish(event)

    # --- consumer lifecycle ---------------------------------------------------
    async def _ensure_group(self) -> None:
        if self._group_ready:
            return
        try:
            await self._provider.client().xgroup_create(
                self._stream, self._group, id="$", mkstream=True
            )
        except Exception as exc:  # BUSYGROUP means it already exists
            if "BUSYGROUP" not in str(exc):
                raise
        self._group_ready = True

    async def run(self) -> None:
        """Consume the stream and dispatch to handlers until :meth:`stop`."""
        await self._ensure_group()
        client = self._provider.client()
        _logger.info("redis_bus_consuming", stream=self._stream, group=self._group)
        while not self._stop.is_set():
            try:
                response = await client.xreadgroup(
                    self._group,
                    self._consumer,
                    {self._stream: ">"},
                    count=self._batch,
                    block=self._block_ms,
                )
            except Exception as exc:  # keep the loop alive on transient errors
                _logger.warning("redis_bus_read_failed", error=str(exc))
                await asyncio.sleep(1.0)
                continue
            if not response:
                continue
            for _stream, messages in response:
                for message_id, fields in messages:
                    await self._dispatch(fields)
                    await client.xack(  # type: ignore[no-untyped-call]
                        self._stream, self._group, message_id
                    )

    async def _dispatch(self, fields: dict[str, Any]) -> None:
        event_type = fields.get("type", "")
        handlers = self._handlers.get(event_type)
        if not handlers:
            return
        try:
            envelope = orjson.loads(fields["data"])
        except Exception as exc:
            _logger.error("redis_bus_bad_envelope", error=str(exc))
            return
        event = self._registry.rebuild(envelope)
        if event is None:
            _logger.debug("redis_bus_unknown_event", event_type=event_type)
            return
        for handler in handlers:
            try:
                await handler(event)
            except Exception as exc:  # one bad handler must not block others
                _logger.error("event_handler_failed", event_type=event_type, error=str(exc))

    def stop(self) -> None:
        self._stop.set()

"""Event-driven + event-sourcing infrastructure.

- :class:`EventBus` — publish/subscribe transport (in-memory or Redis Streams).
- :class:`EventStore` — append-only persistence of every domain event.
"""

from hades.shared_kernel.events.bus import (
    EventBus,
    EventHandler,
    InMemoryEventBus,
)
from hades.shared_kernel.events.redis_bus import RedisEventBus
from hades.shared_kernel.events.registry import EventRegistry
from hades.shared_kernel.events.store import (
    EventStore,
    InMemoryEventStore,
    StoredEvent,
)

__all__ = [
    "EventBus",
    "EventHandler",
    "EventRegistry",
    "EventStore",
    "InMemoryEventBus",
    "InMemoryEventStore",
    "RedisEventBus",
    "StoredEvent",
]

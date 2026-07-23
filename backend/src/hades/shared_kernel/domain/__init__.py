"""DDD tactical building blocks: entities, aggregates, value objects, events."""

from hades.shared_kernel.domain.base import (
    AggregateRoot,
    Entity,
    ValueObject,
)
from hades.shared_kernel.domain.events import DomainEvent
from hades.shared_kernel.domain.identifiers import EntityId, new_id

__all__ = [
    "AggregateRoot",
    "DomainEvent",
    "Entity",
    "EntityId",
    "ValueObject",
    "new_id",
]

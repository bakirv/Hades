"""Strongly-typed identifiers.

Every aggregate has an opaque, globally-unique id. We use UUIDv7 (time-ordered)
so ids sort chronologically — friendlier for event-store indexing and debugging
than random UUIDv4, while still collision-free across services.
"""

from __future__ import annotations

import os
import time
from typing import Any
from uuid import UUID

from pydantic import GetCoreSchemaHandler
from pydantic_core import core_schema


class EntityId(str):
    """A UUID rendered as a string. Behaves like ``str`` for serialisation but
    carries semantic intent in signatures (``token_id: EntityId``)."""

    __slots__ = ()

    def __new__(cls, value: str | UUID) -> EntityId:
        # Validate it is a real UUID; store canonical string form.
        return super().__new__(cls, str(UUID(str(value))))

    @classmethod
    def __get_pydantic_core_schema__(
        cls, _source: type[Any], _handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        """Teach pydantic v2 to validate/serialise ``EntityId`` as a string that
        is coerced (and UUID-validated) through the constructor."""
        return core_schema.no_info_after_validator_function(
            cls,
            core_schema.str_schema(),
            serialization=core_schema.plain_serializer_function_ser_schema(str),
        )


def _uuid7() -> UUID:
    """Generate a UUIDv7 (RFC 9562) without external dependencies.

    Layout: 48-bit unix-millis timestamp | version | 74 random bits.
    """
    unix_ms = int(time.time() * 1000)
    rand = os.urandom(10)
    ts = unix_ms.to_bytes(6, "big")
    # version 7 in the high nibble of byte 6
    b6 = (0x70 | (rand[0] & 0x0F)).to_bytes(1, "big")
    # variant (10xx) in the high bits of byte 8
    b8 = (0x80 | (rand[2] & 0x3F)).to_bytes(1, "big")
    raw = ts + b6 + rand[1:2] + b8 + rand[3:]
    return UUID(bytes=raw[:16])


def new_id() -> EntityId:
    """Mint a fresh, time-ordered entity id."""
    return EntityId(_uuid7())


def uuid7() -> UUID:
    """Mint a fresh, time-ordered ``UUID`` (for ORM column defaults)."""
    return _uuid7()

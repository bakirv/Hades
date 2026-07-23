"""Redis connection provider and ephemeral primitives.

Hades uses Redis for **transient** concerns only — caching, distributed locks,
work queues, rate limiting and pub/sub. It is never a source of truth (that is
PostgreSQL). Every key written here is expected to be expendable and, wherever
it represents state, carries a TTL.

The provider owns a single lazily-created async client; the primitives
(:class:`CacheService`, :class:`DistributedLock`, :class:`RateLimiter`,
:class:`RedisQueue`) compose over it. The concrete ``redis`` import is confined
to this module so the rest of the platform depends only on these abstractions.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from types import TracebackType
from typing import Any

import orjson
import redis.asyncio as aioredis

from hades.shared_kernel.logging import get_logger

_logger = get_logger("cache.redis")

# Atomically release a lock only if we still own it (compare token, then delete).
_UNLOCK_LUA = (
    "if redis.call('get', KEYS[1]) == ARGV[1] then "
    "return redis.call('del', KEYS[1]) else return 0 end"
)


class RedisProvider:
    """Owns the async Redis client. One per process, created on first use."""

    def __init__(self, dsn: str, *, timeout_seconds: float = 5.0) -> None:
        self._dsn = dsn
        self._timeout = timeout_seconds
        self._client: aioredis.Redis[str] | None = None

    def client(self) -> aioredis.Redis[str]:
        if self._client is None:
            self._client = aioredis.from_url(
                self._dsn,
                encoding="utf-8",
                decode_responses=True,
                socket_timeout=self._timeout,
                socket_connect_timeout=self._timeout,
            )
        return self._client

    async def ping(self) -> bool:
        """Return True if Redis answers (used by the health probe)."""
        try:
            return bool(await self.client().ping())
        except Exception as exc:  # probe must never raise
            _logger.warning("redis_ping_failed", error=str(exc))
            return False

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()  # type: ignore[attr-defined]
            self._client = None


class CacheService:
    """JSON cache with mandatory TTL — nothing here is permanent."""

    def __init__(self, provider: RedisProvider, *, namespace: str = "cache") -> None:
        self._provider = provider
        self._ns = namespace

    def _key(self, key: str) -> str:
        return f"{self._ns}:{key}"

    async def get(self, key: str) -> Any | None:
        raw = await self._provider.client().get(self._key(key))
        return orjson.loads(raw) if raw is not None else None

    async def set(self, key: str, value: Any, *, ttl_seconds: int) -> None:
        await self._provider.client().set(self._key(key), orjson.dumps(value), ex=ttl_seconds)

    async def delete(self, key: str) -> None:
        await self._provider.client().delete(self._key(key))


class DistributedLock:
    """A best-effort distributed lock (SET NX PX + safe token release).

    Use as an async context manager::

        async with DistributedLock(provider, "scanner:pumpfun", ttl_ms=30000) as ok:
            if ok:
                ...  # single owner runs the critical section
    """

    def __init__(self, provider: RedisProvider, name: str, *, ttl_ms: int = 30_000) -> None:
        self._provider = provider
        self._key = f"lock:{name}"
        self._ttl_ms = ttl_ms
        self._token = uuid.uuid4().hex
        self._acquired = False

    async def acquire(self) -> bool:
        ok = await self._provider.client().set(self._key, self._token, nx=True, px=self._ttl_ms)
        self._acquired = bool(ok)
        return self._acquired

    async def release(self) -> None:
        if self._acquired:
            await self._provider.client().eval(  # type: ignore[no-untyped-call]
                _UNLOCK_LUA, 1, self._key, self._token
            )
            self._acquired = False

    async def __aenter__(self) -> bool:
        return await self.acquire()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.release()


class RateLimiter:
    """Fixed-window rate limiter (INCR + EXPIRE). Ephemeral counters only."""

    def __init__(self, provider: RedisProvider) -> None:
        self._provider = provider

    async def allow(self, key: str, *, limit: int, window_seconds: int) -> bool:
        redis_key = f"ratelimit:{key}"
        client = self._provider.client()
        count = await client.incr(redis_key)
        if count == 1:
            await client.expire(redis_key, window_seconds)
        return count <= limit


class RedisQueue:
    """A simple durable-enough work queue (LPUSH producer / BRPOP consumer)."""

    def __init__(self, provider: RedisProvider, name: str) -> None:
        self._provider = provider
        self._key = f"queue:{name}"

    async def push(self, item: Any) -> None:
        await self._provider.client().lpush(self._key, orjson.dumps(item))

    async def pop(self, *, timeout_seconds: int = 5) -> Any | None:
        result = await self._provider.client().brpop([self._key], timeout=timeout_seconds)
        if result is None:
            return None
        _, raw = result
        return orjson.loads(raw)

    async def length(self) -> int:
        return int(await self._provider.client().llen(self._key))


class PubSub:
    """Thin publish/subscribe helper over Redis pub/sub channels."""

    def __init__(self, provider: RedisProvider) -> None:
        self._provider = provider

    async def publish(self, channel: str, message: Any) -> None:
        await self._provider.client().publish(channel, orjson.dumps(message))

    async def subscribe(self, channel: str) -> AsyncIterator[Any]:
        pubsub = self._provider.client().pubsub()
        await pubsub.subscribe(channel)
        try:
            async for message in pubsub.listen():
                if message.get("type") == "message":
                    yield orjson.loads(message["data"])
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()  # type: ignore[attr-defined]

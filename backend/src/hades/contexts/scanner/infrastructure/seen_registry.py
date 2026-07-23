"""Seen-token registry adapters (dedup).

Redis holds the dedup set — this is *transient* state (a mint stays "seen" for a
TTL window), exactly what Redis is for; it is never the system of record. An
in-memory implementation backs the tests.
"""

from __future__ import annotations

from hades.contexts.common.domain.value_objects import TokenRef
from hades.shared_kernel.cache import RedisProvider


class RedisSeenTokenRegistry:
    """Dedup via Redis keys with a TTL (``SCANNER_DEDUP_TTL_SECONDS``)."""

    def __init__(
        self, provider: RedisProvider, *, ttl_seconds: int = 86_400, namespace: str = "scanner:seen"
    ) -> None:
        self._provider = provider
        self._ttl = ttl_seconds
        self._ns = namespace

    def _key(self, token: TokenRef) -> str:
        return f"{self._ns}:{token.mint}"

    async def is_new(self, token: TokenRef) -> bool:
        exists = await self._provider.client().exists(self._key(token))
        return exists == 0

    async def mark_seen(self, token: TokenRef) -> None:
        await self._provider.client().set(self._key(token), "1", ex=self._ttl)


class InMemorySeenTokenRegistry:
    """In-process dedup set (tests / single-process runs)."""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    async def is_new(self, token: TokenRef) -> bool:
        return str(token.mint) not in self._seen

    async def mark_seen(self, token: TokenRef) -> None:
        self._seen.add(str(token.mint))

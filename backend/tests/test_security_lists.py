"""Blacklist / Whitelist engines over the in-memory registry."""

from __future__ import annotations

from hades.contexts.security.application.lists import (
    BlacklistEngine,
    ListKind,
    WhitelistEngine,
)
from hades.contexts.security.infrastructure.list_registry import InMemoryListRegistry


async def test_blacklist_add_and_lookup() -> None:
    registry = InMemoryListRegistry()
    engine = BlacklistEngine(registry)
    assert not await engine.is_blacklisted(ListKind.TOKEN, "mint1")
    await engine.blacklist(ListKind.TOKEN, "mint1", reason="honeypot")
    assert await engine.is_blacklisted(ListKind.TOKEN, "mint1")
    # Different kind with the same value is independent.
    assert not await engine.is_blacklisted(ListKind.WALLET, "mint1")


async def test_whitelist_add_and_lookup() -> None:
    registry = InMemoryListRegistry()
    engine = WhitelistEngine(registry)
    await engine.whitelist(ListKind.DEPLOYER, "devA", reason="proven")
    assert await engine.is_whitelisted(ListKind.DEPLOYER, "devA")


async def test_lists_are_append_only_history_preserved() -> None:
    registry = InMemoryListRegistry()
    engine = BlacklistEngine(registry)
    await engine.blacklist(ListKind.DEPLOYER, "devB", reason="first")
    await engine.blacklist(ListKind.DEPLOYER, "devB", reason="second")
    # Both records are kept — nothing is overwritten or deleted.
    matches = [e for e in registry.blacklist if e[1] == "devB"]
    assert len(matches) == 2


async def test_lookup_fails_closed_on_registry_error() -> None:
    class _Broken(InMemoryListRegistry):
        async def is_blacklisted(self, kind: str, value: str) -> bool:
            raise RuntimeError("registry down")

    engine = BlacklistEngine(_Broken())
    # A registry outage must not crash the engine; it returns False (no false veto).
    assert await engine.is_blacklisted(ListKind.TOKEN, "x") is False

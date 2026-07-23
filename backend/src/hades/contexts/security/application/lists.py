"""Blacklist & Whitelist engines — dynamic, append-only reputation lists.

Two mirror-image services over the same :class:`ListRegistry` port:

* **Blacklist** — wallets, developers, tokens, contracts, pools, RPCs and
  domains known to be malicious. A blacklist hit is an immediate veto. History is
  never deleted: entries can be deactivated, but the record of *why* something
  was blocked survives forever (audit + training data).
* **Whitelist** — positive reputation: proven wallets, trusted developers, solid
  projects, well-known protocols. A whitelist hit adds a positive signal (and, on
  the token itself, can waive soft doubts) but can **never** override a critical
  security flag — safety is a floor, not something reputation can buy back.

Neither engine decides trades; they only inform the score.
"""

from __future__ import annotations

from enum import StrEnum

from hades.contexts.security.domain.ports import ListRegistry
from hades.shared_kernel.logging import get_logger

_logger = get_logger("security.lists")


class ListKind(StrEnum):
    """The subject kinds the reputation lists track."""

    TOKEN = "token"
    DEPLOYER = "deployer"
    WALLET = "wallet"
    POOL = "pool"
    CONTRACT = "contract"
    RPC = "rpc"
    DOMAIN = "domain"


class BlacklistEngine:
    """Reads and grows the malicious-subject list."""

    def __init__(self, registry: ListRegistry) -> None:
        self._registry = registry

    async def is_blacklisted(self, kind: ListKind, value: str) -> bool:
        try:
            return await self._registry.is_blacklisted(kind.value, value)
        except Exception as exc:  # a list outage must fail closed, never crash
            _logger.warning("blacklist_lookup_failed", kind=kind.value, error=str(exc))
            return False

    async def blacklist(
        self, kind: ListKind, value: str, *, reason: str, source: str = "engine"
    ) -> None:
        await self._registry.add_blacklist(kind.value, value, reason=reason, source=source)
        _logger.info("blacklisted", kind=kind.value, value=value, reason=reason)


class WhitelistEngine:
    """Reads and grows the trusted-subject list."""

    def __init__(self, registry: ListRegistry) -> None:
        self._registry = registry

    async def is_whitelisted(self, kind: ListKind, value: str) -> bool:
        try:
            return await self._registry.is_whitelisted(kind.value, value)
        except Exception as exc:
            _logger.warning("whitelist_lookup_failed", kind=kind.value, error=str(exc))
            return False

    async def whitelist(
        self, kind: ListKind, value: str, *, reason: str, source: str = "manual"
    ) -> None:
        await self._registry.add_whitelist(kind.value, value, reason=reason, source=source)
        _logger.info("whitelisted", kind=kind.value, value=value, reason=reason)

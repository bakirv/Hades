"""Wallet-observation assembler — turns a security verdict into observations.

This is the I/O boundary for the intelligence context. It reads what the Security
Engine already established about a token (its deployer and top holders, straight
from the assessment facts — no duplicate RPC) and, when live lookups are enabled,
enriches each wallet with its funders so the Cluster Builder can find coordinated
entities. Everything downstream (profiler, engines) is then a pure function of
the batch it returns.

Missing data degrades gracefully: with live lookups off, wallets are still
registered and profiled, just without funding-based clustering.
"""

from __future__ import annotations

from datetime import UTC, datetime

from hades.contexts.intelligence.domain.models import (
    WalletObservation,
    WalletObservationBatch,
    WalletRole,
)
from hades.contexts.intelligence.domain.ports import WalletChainReader
from hades.contexts.security.domain.events import SecurityScoreComputed
from hades.shared_kernel.logging import get_logger

_logger = get_logger("intelligence.assembler")


class WalletObservationAssembler:
    """Builds a :class:`WalletObservationBatch` from a ``SecurityScoreComputed``."""

    def __init__(
        self,
        *,
        reader: WalletChainReader | None = None,
        live_lookups: bool = True,
        top_holders: int = 20,
        max_funder_lookups: int = 8,
        funders_per_wallet: int = 6,
        known_exchanges: frozenset[str] = frozenset(),
        known_mixers: frozenset[str] = frozenset(),
    ) -> None:
        self._reader = reader
        self._live = live_lookups and reader is not None
        self._top_holders = top_holders
        self._max_funder_lookups = max_funder_lookups
        self._funders_per_wallet = funders_per_wallet
        self._known_exchanges = known_exchanges
        self._known_mixers = known_mixers

    async def build(self, event: SecurityScoreComputed) -> WalletObservationBatch:
        now = datetime.now(UTC)
        facts = event.assessment.facts
        deployer, deployer_scammer = _deployer(facts)
        holders = _top_holders(facts, limit=self._top_holders)

        known_scammers: set[str] = set()
        if deployer is not None and deployer_scammer:
            known_scammers.add(deployer)

        # Assemble the wallet list: deployer (if any) + top holders, deduped.
        pct_by_wallet = dict(holders)
        wallets: list[tuple[str, WalletRole, float]] = []
        if deployer is not None:
            wallets.append((deployer, WalletRole.DEPLOYER, pct_by_wallet.get(deployer, 0.0)))
        for owner, pct in holders:
            if owner == deployer:
                continue
            wallets.append((owner, WalletRole.HOLDER, pct))

        funders_map = await self._resolve_funders([w for w, _, _ in wallets])

        observations = tuple(
            WalletObservation(
                address=address,
                role=role,
                pct_supply=pct,
                funders=tuple(funders_map.get(address, ())),
                is_known_scammer=address in known_scammers,
                at=now,
            )
            for address, role, pct in wallets
        )
        return WalletObservationBatch(
            token=event.token,
            now=now,
            observations=observations,
            known_scammers=frozenset(known_scammers),
            known_exchanges=self._known_exchanges,
            known_mixers=self._known_mixers,
        )

    async def _resolve_funders(self, wallets: list[str]) -> dict[str, list[str]]:
        if not self._live or self._reader is None:
            return {}
        result: dict[str, list[str]] = {}
        for address in wallets[: self._max_funder_lookups]:
            try:
                result[address] = await self._reader.funders(
                    address, limit=self._funders_per_wallet
                )
            except Exception as exc:  # a funder lookup failing is not fatal
                _logger.warning("funder_lookup_failed", address=address, error=str(exc))
        return result


def _deployer(facts: dict[str, object]) -> tuple[str | None, bool]:
    dev = facts.get("developer")
    if not isinstance(dev, dict):
        return None, False
    deployer = dev.get("deployer")
    scammer = bool(dev.get("is_known_scammer", False))
    return (deployer if isinstance(deployer, str) else None), scammer


def _top_holders(facts: dict[str, object], *, limit: int) -> list[tuple[str, float]]:
    holder = facts.get("holder")
    if not isinstance(holder, dict):
        return []
    top = holder.get("top_holders")
    if not isinstance(top, list):
        return []
    result: list[tuple[str, float]] = []
    for entry in top[:limit]:
        if not isinstance(entry, dict):
            continue
        owner = entry.get("owner")
        pct = entry.get("pct", 0.0)
        if isinstance(owner, str) and isinstance(pct, int | float):
            result.append((owner, float(pct)))
    return result

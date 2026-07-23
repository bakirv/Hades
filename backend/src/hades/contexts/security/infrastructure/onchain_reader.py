"""On-chain reader — authoritative Solana reads via the RPC Manager.

Turns raw JSON-RPC into the typed facts the analyzers need: the mint account
(authorities, supply, program, Token-2022 extensions), the largest holders with
their owners and supply shares, LP burn/lock coverage, and — for clustering — the
wallets that funded an address. Every method is best-effort: any failure returns
``None`` / empty so the assembler degrades to doubt rather than crashing.

The RPC Manager already handles multi-provider failover, rate limits and health,
so this adapter only parses.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from hades.contexts.security.domain.models import (
    HolderBalance,
    MintAccount,
    TokenProgram,
)
from hades.shared_kernel.logging import get_logger
from hades.shared_kernel.solana import RpcManager

_logger = get_logger("security.onchain")

_SPL_TOKEN = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
_TOKEN_2022 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"

# Addresses that count LP (or supply) as provably removed from circulation.
_BURN_OWNERS = frozenset(
    {
        "1nc1nerator11111111111111111111111111111111",
        "11111111111111111111111111111111",
    }
)
# Well-known LP locker programs (token accounts they own count as "locked").
_LOCKER_OWNERS = frozenset(
    {
        "5v2WTz1qXtFq3JU7hbRHZWrRAxbwLwZzWNJqPvEP7q5V",  # placeholder locker id
    }
)


def _program(owner: str) -> TokenProgram:
    if owner == _SPL_TOKEN:
        return TokenProgram.SPL_TOKEN
    if owner == _TOKEN_2022:
        return TokenProgram.TOKEN_2022
    return TokenProgram.UNKNOWN


def _to_decimal(raw: Any) -> Decimal | None:
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError):
        return None


class RpcOnChainReader:
    """Reads token facts through the shared :class:`RpcManager`."""

    def __init__(self, rpc: RpcManager) -> None:
        self._rpc = rpc

    async def get_mint_account(self, mint: str) -> MintAccount | None:
        try:
            result = await self._rpc.call("getAccountInfo", [mint, {"encoding": "jsonParsed"}])
        except Exception as exc:
            _logger.warning("mint_account_read_failed", mint=mint, error=str(exc))
            return None
        value = (result or {}).get("value") if isinstance(result, dict) else None
        if not isinstance(value, dict):
            return None
        owner = str(value.get("owner", ""))
        parsed = ((value.get("data") or {}).get("parsed")) or {}
        info = parsed.get("info") or {}
        if not isinstance(info, dict):
            info = {}
        decimals = info.get("decimals")
        supply = _to_decimal(info.get("supply")) or Decimal(0)
        extensions = self._extensions(info)
        return MintAccount(
            mint=mint,
            decimals=decimals if isinstance(decimals, int) else 0,
            supply=supply,
            mint_authority=info.get("mintAuthority"),
            freeze_authority=info.get("freezeAuthority"),
            owner_program=owner,
            program=_program(owner),
            is_initialized=parsed.get("type", "mint") == "mint",
            extensions=extensions,
        )

    @staticmethod
    def _extensions(info: dict[str, Any]) -> tuple[str, ...]:
        raw = info.get("extensions")
        if not isinstance(raw, list):
            return ()
        names: list[str] = []
        for ext in raw:
            if isinstance(ext, dict) and isinstance(ext.get("extension"), str):
                names.append(ext["extension"])
        return tuple(names)

    async def get_largest_holders(self, mint: str, *, limit: int = 20) -> list[HolderBalance]:
        try:
            largest = await self._rpc.call("getTokenLargestAccounts", [mint])
            supply_res = await self._rpc.call("getTokenSupply", [mint])
        except Exception as exc:
            _logger.warning("holders_read_failed", mint=mint, error=str(exc))
            return []
        accounts = (largest or {}).get("value") if isinstance(largest, dict) else None
        if not isinstance(accounts, list):
            return []
        supply = self._ui_amount(supply_res)
        owners = await self._resolve_owners(
            [a.get("address") for a in accounts[:limit] if isinstance(a, dict)]
        )
        holders: list[HolderBalance] = []
        for account in accounts[:limit]:
            if not isinstance(account, dict):
                continue
            amount = self._ui_amount({"value": account})
            addr = str(account.get("address", ""))
            owner = owners.get(addr, addr)
            pct = float(amount / supply * 100) if supply and supply > 0 else 0.0
            holders.append(HolderBalance(owner=owner, amount=amount, pct=pct))
        return holders

    async def _resolve_owners(self, token_accounts: list[Any]) -> dict[str, str]:
        addrs = [a for a in token_accounts if isinstance(a, str)]
        if not addrs:
            return {}
        try:
            res = await self._rpc.call("getMultipleAccounts", [addrs, {"encoding": "jsonParsed"}])
        except Exception:
            return {}
        values = (res or {}).get("value") if isinstance(res, dict) else None
        if not isinstance(values, list):
            return {}
        owners: dict[str, str] = {}
        for addr, val in zip(addrs, values, strict=False):
            if isinstance(val, dict):
                info = (((val.get("data") or {}).get("parsed")) or {}).get("info") or {}
                owner = info.get("owner")
                if isinstance(owner, str):
                    owners[addr] = owner
        return owners

    async def get_holder_count(self, mint: str) -> int | None:
        # A precise holder count needs a full getProgramAccounts scan, which most
        # public RPCs reject or throttle heavily. We attempt it but treat failure
        # as "unknown" rather than blocking analysis.
        try:
            res = await self._rpc.call(
                "getProgramAccounts",
                [
                    _SPL_TOKEN,
                    {
                        "encoding": "base64",
                        "dataSlice": {"offset": 0, "length": 0},
                        "filters": [
                            {"dataSize": 165},
                            {"memcmp": {"offset": 0, "bytes": mint}},
                        ],
                    },
                ],
            )
        except Exception:
            return None
        return len(res) if isinstance(res, list) else None

    async def get_lp_secure_pct(self, lp_mint: str) -> tuple[float | None, float | None]:
        try:
            supply_res = await self._rpc.call("getTokenSupply", [lp_mint])
            largest = await self._rpc.call("getTokenLargestAccounts", [lp_mint])
        except Exception as exc:
            _logger.warning("lp_read_failed", lp_mint=lp_mint, error=str(exc))
            return None, None
        supply = self._ui_amount(supply_res)
        accounts = (largest or {}).get("value") if isinstance(largest, dict) else None
        if not isinstance(accounts, list) or not supply or supply <= 0:
            return None, None
        owners = await self._resolve_owners(
            [a.get("address") for a in accounts if isinstance(a, dict)]
        )
        burned = Decimal(0)
        locked = Decimal(0)
        for account in accounts:
            if not isinstance(account, dict):
                continue
            amount = self._ui_amount({"value": account})
            owner = owners.get(str(account.get("address", "")), "")
            if owner in _BURN_OWNERS:
                burned += amount
            elif owner in _LOCKER_OWNERS:
                locked += amount
        burned_pct = float(burned / supply * 100)
        locked_pct = float(locked / supply * 100)
        return burned_pct, locked_pct

    async def get_funders(self, wallet: str, *, limit: int = 25) -> list[str]:
        try:
            sigs = await self._rpc.call("getSignaturesForAddress", [wallet, {"limit": limit}])
        except Exception:
            return []
        if not isinstance(sigs, list) or not sigs:
            return []
        # Inspect the oldest transaction: the wallet's funding usually predates
        # its activity. Bounded to a single getTransaction to cap RPC cost.
        oldest = sigs[-1]
        signature = oldest.get("signature") if isinstance(oldest, dict) else None
        if not isinstance(signature, str):
            return []
        try:
            tx = await self._rpc.call(
                "getTransaction",
                [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}],
            )
        except Exception:
            return []
        return self._funders_from_tx(tx, wallet)

    @staticmethod
    def _funders_from_tx(tx: Any, wallet: str) -> list[str]:
        if not isinstance(tx, dict):
            return []
        message = ((tx.get("transaction") or {}).get("message")) or {}
        instructions = message.get("instructions") or []
        funders: list[str] = []
        for ins in instructions:
            if not isinstance(ins, dict):
                continue
            parsed = ins.get("parsed")
            if not isinstance(parsed, dict):
                continue
            info = parsed.get("info") or {}
            if parsed.get("type") in {"transfer", "transferChecked"} and (
                info.get("destination") == wallet or info.get("newAccount") == wallet
            ):
                source = info.get("source") or info.get("lamports", {})
                if isinstance(source, str):
                    funders.append(source)
        return funders

    @staticmethod
    def _ui_amount(res: Any) -> Decimal:
        """Extract a uiAmount-style balance from a getTokenSupply / account value.

        Prefers the human ``uiAmountString`` and falls back to the raw ``amount``;
        returns ``Decimal(0)`` when neither is present or parseable.
        """
        if not isinstance(res, dict):
            return Decimal(0)
        value = res.get("value")
        if not isinstance(value, dict):
            return Decimal(0)
        ui_str = value.get("uiAmountString")
        dec = _to_decimal(ui_str) if ui_str is not None else _to_decimal(value.get("amount"))
        return dec if dec is not None else Decimal(0)


class InMemoryOnChainReader:
    """Deterministic on-chain reader for tests — returns pre-loaded facts."""

    def __init__(
        self,
        *,
        mint_accounts: dict[str, MintAccount] | None = None,
        holders: dict[str, list[HolderBalance]] | None = None,
        holder_counts: dict[str, int] | None = None,
        lp_secure: dict[str, tuple[float | None, float | None]] | None = None,
        funders: dict[str, list[str]] | None = None,
    ) -> None:
        self._mints = mint_accounts or {}
        self._holders = holders or {}
        self._counts = holder_counts or {}
        self._lp = lp_secure or {}
        self._funders = funders or {}

    async def get_mint_account(self, mint: str) -> MintAccount | None:
        return self._mints.get(mint)

    async def get_largest_holders(self, mint: str, *, limit: int = 20) -> list[HolderBalance]:
        return self._holders.get(mint, [])[:limit]

    async def get_holder_count(self, mint: str) -> int | None:
        return self._counts.get(mint)

    async def get_lp_secure_pct(self, lp_mint: str) -> tuple[float | None, float | None]:
        return self._lp.get(lp_mint, (None, None))

    async def get_funders(self, wallet: str, *, limit: int = 25) -> list[str]:
        return self._funders.get(wallet, [])[:limit]

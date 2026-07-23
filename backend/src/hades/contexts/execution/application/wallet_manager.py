"""Wallet Manager — the platform's view of the trading wallet.

Owns the wallet's *identity and health*, never its secrets. It exposes the
public key, the SOL balance (read via RPC) and a health verdict (configured,
reachable, funded). It NEVER touches, logs or returns private-key material — the
keypair lives only inside the :class:`TransactionSigner` adapter, loaded from a
mounted secret. In paper mode the wallet is not required, so a missing wallet is
not an error; it only blocks the live-readiness gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from hades.contexts.execution.domain.ports import RpcGateway
from hades.shared_kernel.config.settings import WalletSettings
from hades.shared_kernel.logging import get_logger

_logger = get_logger("execution.wallet")
_LAMPORTS_PER_SOL = Decimal(10) ** 9


@dataclass(frozen=True)
class WalletHealth:
    configured: bool
    reachable: bool
    balance_sol: float
    public_key: str | None
    healthy: bool
    detail: str


class WalletManager:
    """Reads wallet identity, balance and health — no key material ever."""

    def __init__(
        self,
        settings: WalletSettings,
        *,
        rpc: RpcGateway | None = None,
        min_balance_sol: float = 0.01,
    ) -> None:
        self._settings = settings
        self._rpc = rpc
        self._min_balance_sol = min_balance_sol

    @property
    def public_key(self) -> str | None:
        return self._settings.public_key or None

    @property
    def is_configured(self) -> bool:
        return self._settings.is_configured

    async def balance_sol(self) -> float | None:
        """Fetch the wallet SOL balance via RPC, or ``None`` if unavailable."""
        if not self._settings.is_configured or self._rpc is None:
            return None
        try:
            result = await self._rpc.call("getBalance", [self._settings.public_key])
            lamports = _extract_lamports(result)
            if lamports is None:
                return None
            return float(Decimal(lamports) / _LAMPORTS_PER_SOL)
        except Exception as exc:  # health probe must never raise
            _logger.warning("wallet_balance_failed", error=str(exc))
            return None

    async def health(self) -> WalletHealth:
        configured = self._settings.is_configured
        balance = await self.balance_sol()
        reachable = balance is not None
        funded = balance is not None and balance >= self._min_balance_sol
        healthy = configured and reachable and funded
        if not configured:
            detail = "wallet not configured (paper mode ok)"
        elif not reachable:
            detail = "wallet unreachable via RPC"
        elif not funded:
            detail = f"balance {balance:.4f} SOL below minimum {self._min_balance_sol}"
        else:
            detail = "wallet healthy"
        return WalletHealth(
            configured=configured,
            reachable=reachable,
            balance_sol=balance or 0.0,
            public_key=self.public_key,
            healthy=healthy,
            detail=detail,
        )


def _extract_lamports(result: object) -> int | None:
    """getBalance returns ``{"value": <lamports>}`` or a bare int, per client."""
    if isinstance(result, dict):
        value = result.get("value")
        return int(value) if isinstance(value, int) else None
    if isinstance(result, int):
        return result
    return None

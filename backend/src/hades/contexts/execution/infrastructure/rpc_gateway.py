"""Adapter binding the shared RPC Manager to the execution ``RpcGateway`` port.

Keeps the execution context depending on its own narrow port rather than the
concrete :class:`~hades.shared_kernel.solana.rpc_manager.RpcManager`, so the
live executor and confirmation engine stay infrastructure-agnostic and trivially
fakeable in tests.
"""

from __future__ import annotations

from typing import Any

from hades.shared_kernel.solana.rpc_manager import RpcManager


class RpcManagerGateway:
    """Wraps :class:`RpcManager` to satisfy the ``RpcGateway`` port."""

    def __init__(self, manager: RpcManager) -> None:
        self._manager = manager

    async def call(self, method: str, params: list[Any] | None = None) -> Any:
        return await self._manager.call(method, params)

    @property
    def active_endpoint(self) -> str | None:
        return self._manager.active_endpoint

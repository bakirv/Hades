"""Shared Solana infrastructure — the RPC access layer used by every context.

The Scanner, Market, Wallet and (later) Execution engines all talk to Solana
through one abstraction: the :class:`RpcManager`. It fans requests across several
configured providers (Helius, QuickNode, Chainstack, Alchemy, a self-hosted
node…), measures each one's latency and failures continuously, and always routes
through the healthiest provider — failing over automatically and reconnecting to
recovered providers. It never trades and never decides; it only moves JSON-RPC
calls to a live endpoint.

This package lives in the shared kernel (pure infrastructure) and imports no
bounded context. Contexts observe endpoint switches through an injected callback,
which they translate into their own domain events.
"""

from __future__ import annotations

from hades.shared_kernel.solana.rpc_manager import (
    EndpointStatus,
    RpcEndpointState,
    RpcManager,
    RpcSwitch,
    RpcTransport,
    RpcUnavailableError,
)

__all__ = [
    "EndpointStatus",
    "RpcEndpointState",
    "RpcManager",
    "RpcSwitch",
    "RpcTransport",
    "RpcUnavailableError",
]

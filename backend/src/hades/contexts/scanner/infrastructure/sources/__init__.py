"""DEX / aggregator discovery-source adapters.

One module per protocol (pump.fun, Raydium, Orca, Meteora, Jupiter,
DexScreener…). Each subclasses :class:`HttpPollingSource` and implements only its
own response parsing — logic is never mixed between DEXes. New protocols are
added by dropping in a new adapter and registering it in :mod:`factory`.
"""

from __future__ import annotations

from hades.contexts.scanner.infrastructure.sources.base import HttpPollingSource
from hades.contexts.scanner.infrastructure.sources.factory import (
    SOURCE_REGISTRY,
    build_sources,
)

__all__ = ["SOURCE_REGISTRY", "HttpPollingSource", "build_sources"]

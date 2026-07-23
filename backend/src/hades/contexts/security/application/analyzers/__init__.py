"""Security analyzers — one module per single responsibility.

Each analyzer is a pure function of the :class:`SecurityInputs` context and
returns an :class:`AnalyzerReport` (a sub-score plus the flags/positives/facts
behind it). The engine composes them; none knows about the others.

``DEFAULT_ANALYZERS`` is the ordered set the engine runs by default. Adding an
analyzer here is the only change needed to extend the Security Engine.
"""

from __future__ import annotations

from hades.contexts.security.application.analyzers.authority import AuthorityAnalyzer
from hades.contexts.security.application.analyzers.behavior import BehaviorAnalyzer
from hades.contexts.security.application.analyzers.contract import ContractAnalyzer
from hades.contexts.security.application.analyzers.developer import DeveloperAnalyzer
from hades.contexts.security.application.analyzers.holder import HolderAnalyzer
from hades.contexts.security.application.analyzers.honeypot import HoneypotAnalyzer
from hades.contexts.security.application.analyzers.liquidity import LiquidityAnalyzer
from hades.contexts.security.application.analyzers.pool import PoolAnalyzer
from hades.contexts.security.application.analyzers.transaction import TransactionAnalyzer
from hades.contexts.security.application.analyzers.wallet_cluster import (
    WalletClusterAnalyzer,
)
from hades.contexts.security.domain.ports import SecurityCheck

#: The ordered default set of analyzers the engine composes.
DEFAULT_ANALYZERS: tuple[SecurityCheck, ...] = (
    ContractAnalyzer(),
    AuthorityAnalyzer(),
    LiquidityAnalyzer(),
    PoolAnalyzer(),
    HolderAnalyzer(),
    HoneypotAnalyzer(),
    DeveloperAnalyzer(),
    WalletClusterAnalyzer(),
    TransactionAnalyzer(),
    BehaviorAnalyzer(),
)

__all__ = [
    "DEFAULT_ANALYZERS",
    "AuthorityAnalyzer",
    "BehaviorAnalyzer",
    "ContractAnalyzer",
    "DeveloperAnalyzer",
    "HolderAnalyzer",
    "HoneypotAnalyzer",
    "LiquidityAnalyzer",
    "PoolAnalyzer",
    "TransactionAnalyzer",
    "WalletClusterAnalyzer",
]

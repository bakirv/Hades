"""Common published language — the shared vocabulary of the trading domain.

These value objects are the *contract types* that travel between contexts inside
domain events (a ``TokenMint``, a ``Money`` amount, a ``Score``, a
``Probability``). They are deliberately domain-shared and immutable. Keeping
them here — rather than duplicating a ``Score`` in every context — is what lets
modules speak the same language without depending on each other's internals.
"""

from hades.contexts.common.domain.value_objects import (
    Confidence,
    Money,
    Percentage,
    Probability,
    Score,
    TokenMint,
    TokenRef,
    WalletAddress,
)

__all__ = [
    "Confidence",
    "Money",
    "Percentage",
    "Probability",
    "Score",
    "TokenMint",
    "TokenRef",
    "WalletAddress",
]

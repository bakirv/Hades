"""Ports (contracts) the Security Engine depends on.

The engine and its analyzers depend on abstractions only. All blockchain / HTTP
I/O is hidden behind these protocols so the domain stays pure and testable:

* :class:`OnChainReader`   — authoritative reads (mint account, largest holders,
  signatures) via the RPC Manager.
* :class:`SwapSimulator`   — buy+sell simulation for honeypot detection.
* :class:`ClusterDetector` — funding-graph clustering of a token's top holders.
* :class:`ListRegistry`    — dynamic, append-only black/white lists.
* :class:`DeveloperReputationStore` — the deployer track record Hades accumulates.
* :class:`SecurityRepository` — persists every assessment (approved *and*
  rejected) for audit and future model training.
* :class:`TokenFactsSource` — stored metadata/pool the Scanner already collected.

Adding an analyzer or swapping an adapter never touches the others.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable

from hades.contexts.common.domain.value_objects import TokenRef, WalletAddress
from hades.contexts.security.domain.models import (
    AnalyzerReport,
    ClusterReport,
    DeveloperReputation,
    HolderBalance,
    HoneypotProbe,
    MintAccount,
    SecurityAssessment,
    SecurityInputs,
)
from hades.shared_kernel.domain.base import ValueObject


class StoredTokenFacts(ValueObject):
    """Read model of the facts the Scanner already persisted for a token.

    The assembler reads these from Postgres and merges them with fresh on-chain
    reads to build the analysis context.
    """

    first_seen_at: datetime | None = None
    has_socials: bool = False
    is_mutable: bool | None = None
    deployer: str | None = None
    pool_address: str | None = None
    pool_dex: str | None = None
    pool_liquidity_usd: Decimal | None = None
    lp_mint: str | None = None


@runtime_checkable
class SecurityCheck(Protocol):
    """A single pure analyzer contributing a sub-score and its reasons.

    The engine composes many checks (contract, authority, liquidity, holders,
    honeypot, developer, clusters…) and aggregates them into one score. Adding a
    check never modifies the others (Open/Closed). ``analyze`` is synchronous and
    side-effect-free — every input it needs was pre-fetched into ``inputs``.
    """

    @property
    def name(self) -> str: ...

    def analyze(self, inputs: SecurityInputs) -> AnalyzerReport: ...


@runtime_checkable
class OnChainReader(Protocol):
    """Authoritative on-chain reads used to build the analysis context.

    Every method is best-effort: return ``None`` / empty on failure so the
    assembler degrades gracefully (missing data becomes doubt, never a pass).
    """

    async def get_mint_account(self, mint: str) -> MintAccount | None: ...

    async def get_largest_holders(self, mint: str, *, limit: int = 20) -> list[HolderBalance]: ...

    async def get_holder_count(self, mint: str) -> int | None: ...

    async def get_lp_secure_pct(self, lp_mint: str) -> tuple[float | None, float | None]:
        """Return ``(burned_pct, locked_pct)`` of an LP mint, when determinable."""
        ...

    async def get_funders(self, wallet: str, *, limit: int = 25) -> list[str]:
        """Wallets that funded ``wallet`` (SOL transfers in), most-recent first."""
        ...


@runtime_checkable
class SwapSimulator(Protocol):
    """Simulates a buy then a sell to detect tokens that cannot be sold."""

    async def probe(self, token: TokenRef, *, amount_usd: float) -> HoneypotProbe: ...


@runtime_checkable
class ClusterDetector(Protocol):
    """Groups a token's top holders into likely single-entity clusters."""

    async def detect(self, token: TokenRef, holders: list[HolderBalance]) -> ClusterReport: ...


@runtime_checkable
class TokenFactsSource(Protocol):
    """Reads facts the Scanner already stored (socials, pool, first-seen)."""

    async def load(self, token: TokenRef) -> StoredTokenFacts | None: ...


@runtime_checkable
class ListRegistry(Protocol):
    """Dynamic, append-only black/white lists across every subject kind.

    History is never deleted: an entry can be deactivated but the record stays,
    so we can always explain why a token was blocked six months ago. ``kind`` is
    one of ``token`` / ``deployer`` / ``wallet`` / ``pool`` / ``domain``.
    """

    async def is_blacklisted(self, kind: str, value: str) -> bool: ...

    async def is_whitelisted(self, kind: str, value: str) -> bool: ...

    async def add_blacklist(
        self, kind: str, value: str, *, reason: str, source: str = "engine"
    ) -> None: ...

    async def add_whitelist(
        self, kind: str, value: str, *, reason: str, source: str = "manual"
    ) -> None: ...


@runtime_checkable
class DeveloperReputationStore(Protocol):
    """Persists and serves the deployer track record accumulated over time."""

    async def get(self, deployer: WalletAddress) -> DeveloperReputation | None: ...

    async def observe_token(self, deployer: WalletAddress, *, mint: str) -> None:
        """Record that ``deployer`` shipped ``mint`` (grows ``tokens_created``)."""
        ...

    async def record_outcome(self, deployer: WalletAddress, *, outcome: str) -> None:
        """Record a resolved outcome for a deployer's token (rug/survived/success)."""
        ...


@runtime_checkable
class SecurityRepository(Protocol):
    """Persists every assessment for audit + research (approved and rejected)."""

    async def save(self, assessment: SecurityAssessment) -> None: ...

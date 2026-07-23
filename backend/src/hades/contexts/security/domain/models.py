"""Security value objects — the vocabulary of the Security Engine.

Nothing here forms a *decision*. These types describe, in structured and
explainable terms, what the engine observed about a token (its authorities, its
holders, its liquidity, its developer's history, the wallet clusters behind it)
and the risk that follows. Every risk is a named :class:`RiskFlag` carrying its
own severity and evidence; every reassurance is a named :class:`PositiveSignal`.
A verdict is always the sum of visible parts — never an opaque number.

The engine is deliberately conservative: a single ``CRITICAL`` flag hard-vetoes a
token regardless of how healthy everything else looks. We would rather miss a
hundred opportunities than enter one rug.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import Field

from hades.contexts.common.domain.value_objects import Score, TokenRef, WalletAddress
from hades.shared_kernel.domain.base import ValueObject

# --- primitives --------------------------------------------------------------


class RiskSeverity(StrEnum):
    """How much a single concern should weigh on the verdict."""

    INFO = "info"  # noted, no penalty (e.g. "no sells observed yet")
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"  # a CRITICAL flag hard-vetoes the token


class RiskFlag(ValueObject):
    """One specific, named security concern with its severity + evidence."""

    code: str  # e.g. "MINT_AUTHORITY_ACTIVE", "LP_NOT_LOCKED"
    severity: RiskSeverity
    detail: str

    @property
    def is_critical(self) -> bool:
        return self.severity is RiskSeverity.CRITICAL


class PositiveSignal(ValueObject):
    """A named reassurance that improves an analyzer's sub-score.

    Positives never *cancel* a critical flag (safety is a floor, not a trade),
    but they are surfaced in the explanation so an approval is as legible as a
    rejection.
    """

    code: str  # e.g. "MINT_RENOUNCED", "LP_BURNED"
    detail: str


# --- on-chain / market facts (pre-fetched by the infrastructure assembler) ---
# Analyzers are pure functions over these facts; they never do I/O themselves.


class TokenProgram(StrEnum):
    """Which token program owns the mint. Token-2022 can carry risky extensions."""

    SPL_TOKEN = "spl_token"
    TOKEN_2022 = "token_2022"
    UNKNOWN = "unknown"


class MintAccount(ValueObject):
    """Authoritative on-chain state of a token's mint account.

    Read fresh at analysis time — the engine never trusts stale metadata for a
    veto decision. ``None`` authorities mean *renounced* (the healthy case).
    """

    mint: str
    decimals: int
    supply: Decimal
    mint_authority: str | None  # None => minting renounced
    freeze_authority: str | None  # None => cannot freeze wallets
    owner_program: str
    program: TokenProgram = TokenProgram.UNKNOWN
    is_initialized: bool = True
    # Token-2022 extensions detected on the mint (transfer fee/hook = honeypot vector).
    extensions: tuple[str, ...] = ()

    @property
    def mint_renounced(self) -> bool:
        return self.mint_authority is None

    @property
    def freeze_renounced(self) -> bool:
        return self.freeze_authority is None


class HolderBalance(ValueObject):
    """One holder's balance and its share of circulating supply."""

    owner: str
    amount: Decimal
    pct: float  # 0..100 share of supply


class LiquidityPool(ValueObject):
    """A liquidity pool plus the LP-lock facts the assembler could establish."""

    address: str
    dex: str
    liquidity_usd: Decimal
    lp_mint: str | None = None
    quote_symbol: str | None = None
    # Share of the LP supply that is provably burned / locked (0..100). The
    # remainder is rug-pullable. ``None`` means "could not be determined".
    lp_burned_pct: float | None = None
    lp_locked_pct: float | None = None
    lock_provider: str | None = None
    lock_until: datetime | None = None
    created_at: datetime | None = None

    @property
    def secured_pct(self) -> float | None:
        """Burned + locked share of LP, when at least one is known."""
        if self.lp_burned_pct is None and self.lp_locked_pct is None:
            return None
        return (self.lp_burned_pct or 0.0) + (self.lp_locked_pct or 0.0)


class HoneypotProbe(ValueObject):
    """Result of simulating a buy and a sell to detect un-sellable tokens.

    ``sellable is None`` means the simulation could not be run (treated as a
    doubt, not a pass). Taxes are in basis points; a large asymmetry between buy
    and sell tax is a classic honeypot tell.
    """

    sellable: bool | None
    buyable: bool | None = None
    buy_tax_bps: int | None = None
    sell_tax_bps: int | None = None
    note: str = ""


class DeveloperReputation(ValueObject):
    """A deployer's accumulated track record, as Hades has observed it.

    Reputation is *earned over time*: the platform records every token a deployer
    ships and how it ended (rug / survived / success). At first sight of a new
    deployer this is empty — an unknown developer is a mild penalty, never a free
    pass. ``is_known_scammer`` is set by the Blacklist Engine.
    """

    deployer: str
    tokens_created: int = 0
    rugs: int = 0
    survived: int = 0
    successes: int = 0
    avg_lifetime_hours: float | None = None
    avg_roi: float | None = None
    is_known_scammer: bool = False

    @property
    def is_known(self) -> bool:
        return self.tokens_created > 0

    @property
    def rug_rate(self) -> float | None:
        if self.tokens_created == 0:
            return None
        return self.rugs / self.tokens_created


class WalletCluster(ValueObject):
    """A set of wallets that appear to be one entity (common funder / timing)."""

    members: tuple[str, ...]
    funder: str | None = None
    pct_supply: float = 0.0  # combined share of supply the cluster controls
    reason: str = "common_funder"


class ClusterReport(ValueObject):
    """The Wallet Cluster Analyzer's finding for a token."""

    clusters: tuple[WalletCluster, ...] = ()
    analysed_wallets: int = 0
    data_complete: bool = True  # False when RPC budget bounded the search

    @property
    def largest_pct(self) -> float:
        return max((c.pct_supply for c in self.clusters), default=0.0)


# --- the analysis context (what analyzers receive) ---------------------------


class SecurityInputs(ValueObject):
    """Everything an analysis needs, pre-fetched once by the assembler.

    Keeping all I/O in the assembler makes every analyzer a *pure function* of
    this bundle: fully deterministic and testable without a network. Any field
    may be ``None`` when its source was unavailable — analyzers treat missing
    data as doubt (a penalty), never as an implicit pass.
    """

    token: TokenRef
    now: datetime
    mint_account: MintAccount | None = None
    holders: tuple[HolderBalance, ...] = ()
    holder_count: int | None = None
    pool: LiquidityPool | None = None
    honeypot: HoneypotProbe | None = None
    developer: DeveloperReputation | None = None
    deployer: WalletAddress | None = None
    cluster: ClusterReport | None = None
    # Selected feature values (namespace.key -> value) from the Feature Engine.
    features: dict[str, float] = Field(default_factory=dict)
    # Age of the token in minutes, when known (drives behaviour heuristics).
    age_minutes: float | None = None
    has_socials: bool = False
    is_mutable: bool | None = None


# --- analyzer output ---------------------------------------------------------


class AnalyzerReport(ValueObject):
    """One analyzer's contribution: a sub-score plus the reasons behind it.

    ``facts`` carries structured evidence for the dashboard and the audit log
    (authorities, top holders, liquidity, clusters…). ``insufficient_data``
    marks that the analyzer ran blind — the engine counts these and, being
    conservative, rejects borderline tokens when too many analyzers were blind.
    """

    name: str
    score: Score
    flags: tuple[RiskFlag, ...] = ()
    positives: tuple[PositiveSignal, ...] = ()
    facts: dict[str, object] = Field(default_factory=dict)
    insufficient_data: bool = False

    @property
    def critical_flags(self) -> tuple[RiskFlag, ...]:
        return tuple(f for f in self.flags if f.is_critical)


# --- the verdict -------------------------------------------------------------


class SecurityDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class Explanation(ValueObject):
    """A fully legible account of why the engine reached its verdict."""

    summary: str
    positives: tuple[str, ...] = ()
    negatives: tuple[str, ...] = ()


class SecurityAssessment(ValueObject):
    """Full security verdict for a token: score, sub-scores and the why.

    This is the only thing the engine emits downstream. It is an *input to* the
    (later) AI Committee — never itself a buy. ``approved`` is the gate: a
    rejected token never reaches scoring.
    """

    token: TokenRef
    decision: SecurityDecision
    score: Score
    sub_scores: dict[str, float] = Field(default_factory=dict)
    flags: tuple[RiskFlag, ...] = ()
    positives: tuple[PositiveSignal, ...] = ()
    explanation: Explanation | None = None
    facts: dict[str, object] = Field(default_factory=dict)
    analyzed_at: datetime | None = None
    duration_ms: float | None = None

    @property
    def approved(self) -> bool:
        return self.decision is SecurityDecision.APPROVED

    @property
    def has_critical_flag(self) -> bool:
        return any(f.is_critical for f in self.flags)

    @property
    def top_reasons(self) -> tuple[str, ...]:
        if self.explanation is None:
            return ()
        return self.explanation.negatives if not self.approved else self.explanation.positives

"""Wallet Intelligence value objects — the vocabulary of the knowledge base.

Everything here is immutable and explainable. A wallet is never reduced to an
opaque number: every score carries the reputation components and the reasons
behind it. Reputation is *evolving and non-binary* — a wallet earns trust and
sheds risk over many observations, it is never simply "good" or "bad".

None of these types decide a trade. They describe what Hades has observed about a
wallet (who it is, what it did, who funded it, who it moves with) and how much,
on the evidence so far, its behaviour should be trusted or feared.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from hades.contexts.common.domain.value_objects import Score, TokenRef, WalletAddress
from hades.shared_kernel.domain.base import ValueObject

# --- enums -------------------------------------------------------------------


class WalletRole(StrEnum):
    """How a wallet related to a specific token when it was observed."""

    DEPLOYER = "deployer"
    EARLY_BUYER = "early_buyer"
    HOLDER = "holder"
    FUNDER = "funder"


class BehaviorType(StrEnum):
    """A wallet's dominant trading style, inferred from its observed activity."""

    UNKNOWN = "unknown"
    SNIPER = "sniper"  # buys within seconds of launch, repeatedly
    SCALPER = "scalper"  # very short holds, high frequency
    SWING = "swing"  # medium holds
    HOLDER = "holder"  # long holds
    MARKET_MAKER = "market_maker"  # two-sided, tight, continuous
    ARBITRAGE = "arbitrage"  # cross-venue, near-instant round trips
    HIGH_FREQUENCY = "high_frequency"  # very many ops per unit time
    WHALE = "whale"  # large capital footprint
    RETAIL = "retail"  # small, infrequent


class FundingSourceKind(StrEnum):
    """The nature of a wallet that funded another wallet."""

    EXCHANGE = "exchange"  # known CEX hot wallet
    MIXER = "mixer"  # known mixer / tumbler (suspicious)
    BRIDGE = "bridge"  # cross-chain bridge
    WALLET = "wallet"  # an ordinary wallet
    SUSPICIOUS = "suspicious"  # blacklisted / flagged funder
    FRESH = "fresh"  # brand-new wallet, no history
    UNKNOWN = "unknown"


class ReputationBand(StrEnum):
    """A coarse label over the final wallet score, for quick reading."""

    SMART_MONEY = "smart_money"
    TRUSTED = "trusted"
    NEUTRAL = "neutral"
    RISKY = "risky"
    DUMB_MONEY = "dumb_money"
    SCAMMER = "scammer"


class MoneyClass(StrEnum):
    """Whether a wallet historically adds or removes predictive edge."""

    SMART = "smart"
    NEUTRAL = "neutral"
    DUMB = "dumb"


# --- reputation --------------------------------------------------------------


class ReputationScores(ValueObject):
    """The evolving, non-binary reputation of a wallet (each component 0-100).

    These are *measured*, not asserted: they start neutral (50) for an unknown
    wallet and move as evidence accrues. ``risk`` is inverted vs the others — a
    high risk is bad, a high trust is good.
    """

    trust: float = Field(default=50.0, ge=0.0, le=100.0)
    risk: float = Field(default=50.0, ge=0.0, le=100.0)
    consistency: float = Field(default=50.0, ge=0.0, le=100.0)
    experience: float = Field(default=0.0, ge=0.0, le=100.0)
    profitability: float = Field(default=50.0, ge=0.0, le=100.0)

    @staticmethod
    def initial() -> ReputationScores:
        """The reputation of a wallet seen for the very first time."""
        return ReputationScores()


# --- funding & relationships -------------------------------------------------


class FundingLink(ValueObject):
    """One inbound funding edge: a wallet that sent SOL to the subject wallet."""

    source: str
    kind: FundingSourceKind = FundingSourceKind.UNKNOWN
    note: str = ""


class Relationship(ValueObject):
    """A directed edge in the wallet graph (funding / co-holding / co-trading)."""

    source: str
    target: str
    kind: str  # e.g. "funded", "co_holder", "same_cluster"
    weight: float = 1.0
    observations: int = 1


class Cluster(ValueObject):
    """A set of wallets that appear to be a single entity.

    Confidence is explicit — clustering is probabilistic. ``reason`` records
    *why* (common funder, synchronized timing, identical sizing…).
    """

    cluster_id: str
    members: tuple[str, ...]
    funder: str | None = None
    reason: str = "common_funder"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    pct_supply: float = 0.0

    @property
    def size(self) -> int:
        return len(self.members)


# --- observations (what the assembler produces) ------------------------------


class WalletObservation(ValueObject):
    """A single observed fact about a wallet, tied to a token.

    Produced by the infrastructure assembler from on-chain reads (top holders,
    the deployer, funders). Pure engines fold these into evolving profiles.
    """

    address: str
    role: WalletRole
    pct_supply: float = 0.0
    funders: tuple[str, ...] = ()
    dex: str | None = None
    is_known_scammer: bool = False
    at: datetime


class WalletObservationBatch(ValueObject):
    """All wallet observations gathered for one analysed token."""

    token: TokenRef
    now: datetime
    observations: tuple[WalletObservation, ...] = ()
    # Addresses (from ``funders``/blacklist) known to be malicious, so pure
    # engines can classify funding without doing any I/O.
    known_scammers: frozenset[str] = frozenset()
    known_exchanges: frozenset[str] = frozenset()
    known_mixers: frozenset[str] = frozenset()


# --- behaviour ---------------------------------------------------------------


class BehaviorProfile(ValueObject):
    """The inferred trading style of a wallet plus the confidence behind it."""

    behavior: BehaviorType = BehaviorType.UNKNOWN
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    detail: str = ""


# --- explainability ----------------------------------------------------------


class WalletExplanation(ValueObject):
    """A fully legible account of why a wallet scored the way it did."""

    summary: str
    positives: tuple[str, ...] = ()
    negatives: tuple[str, ...] = ()


# --- the wallet profile (aggregate read model) -------------------------------


class WalletScoreBreakdown(ValueObject):
    """The component scores that compose the final Wallet Score (each 0-100)."""

    trust: float = 50.0
    risk: float = 50.0
    smart_money: float = 50.0
    consistency: float = 50.0
    influence: float = 50.0
    experience: float = 0.0
    behavior: float = 50.0
    profitability: float = 50.0


class WalletProfile(ValueObject):
    """The accumulated identity of one wallet — the core knowledge-base record.

    A snapshot: the registry/profiler produces a new version each time the wallet
    is observed, and the previous versions are kept forever in the knowledge base.
    Counts only ever grow; scores evolve.
    """

    address: WalletAddress
    first_seen_at: datetime
    last_active_at: datetime
    # Lifetime activity (monotonic).
    observations: int = 0
    tokens_traded: int = 0
    launches: int = 0
    rugs_participated: int = 0
    successes: int = 0
    dexes: tuple[str, ...] = ()
    roles: tuple[str, ...] = ()
    avg_pct_supply: float = 0.0
    # Derived intelligence.
    reputation: ReputationScores = Field(default_factory=ReputationScores.initial)
    behavior: BehaviorProfile = Field(default_factory=BehaviorProfile)
    money_class: MoneyClass = MoneyClass.NEUTRAL
    smart_money_score: Score = Field(default_factory=lambda: Score(value=50.0))
    influence: float = Field(default=0.0, ge=0.0, le=100.0)
    funding: tuple[FundingLink, ...] = ()
    cluster_id: str | None = None
    # Final verdict.
    score: Score = Field(default_factory=lambda: Score(value=50.0))
    band: ReputationBand = ReputationBand.NEUTRAL
    explanation: WalletExplanation | None = None
    version: int = 1

    @property
    def age_hours(self) -> float:
        return max(0.0, (self.last_active_at - self.first_seen_at).total_seconds() / 3600.0)

    @property
    def is_smart_money(self) -> bool:
        return self.money_class is MoneyClass.SMART


class TimelineEntry(ValueObject):
    """One dated event in a wallet's life, for the append-only timeline."""

    address: str
    at: datetime
    kind: str  # e.g. "observed_holder", "launch", "cluster_joined"
    mint: str | None = None
    detail: str = ""


# --- per-token intelligence snapshot (what the engine emits) -----------------


class IntelligenceSnapshot(ValueObject):
    """Wallet-side intelligence aggregated for one analysed token.

    This is the read model the (later) AI Committee consumes: how much smart vs
    dumb money is around this token, the average trust/risk of its wallets, the
    clusters behind it and the funding footprint. It is *information*, never a
    trade instruction.
    """

    token: TokenRef
    wallets_observed: int = 0
    new_wallets: int = 0
    smart_money_count: int = 0
    dumb_money_count: int = 0
    smart_money_pct_supply: float = 0.0
    avg_trust: float = 50.0
    avg_risk: float = 50.0
    avg_influence: float = 0.0
    clusters: tuple[Cluster, ...] = ()
    funding_sources: int = 0
    analyzed_at: datetime | None = None
    duration_ms: float | None = None

    @property
    def cluster_count(self) -> int:
        return len(self.clusters)

    @property
    def largest_cluster_pct(self) -> float:
        return max((c.pct_supply for c in self.clusters), default=0.0)

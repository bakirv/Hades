"""Domain events emitted by Wallet Intelligence.

Every meaningful change in the knowledge base is a fact in the past tense. Other
contexts (and, later, the AI Committee) react to these; nothing here calls into
another context directly.
"""

from __future__ import annotations

from hades.contexts.common.domain.value_objects import TokenRef
from hades.contexts.intelligence.domain.models import (
    Cluster,
    IntelligenceSnapshot,
    WalletProfile,
)
from hades.shared_kernel.domain.events import DomainEvent


class WalletRegistered(DomainEvent):
    """A wallet was seen for the first time and given a permanent identity."""

    aggregate_type: str = "wallet"
    address: str
    first_role: str


class WalletUpdated(DomainEvent):
    """An existing wallet's profile advanced to a new version."""

    aggregate_type: str = "wallet"
    address: str
    version: int


class WalletScoreUpdated(DomainEvent):
    """A wallet's final score changed materially."""

    aggregate_type: str = "wallet"
    address: str
    score: float
    band: str


class ReputationUpdated(DomainEvent):
    """A wallet's reputation components evolved."""

    aggregate_type: str = "wallet"
    address: str
    trust: float
    risk: float


class BehaviorChanged(DomainEvent):
    """A wallet was (re)classified into a different behaviour type."""

    aggregate_type: str = "wallet"
    address: str
    behavior: str
    confidence: float


class SmartMoneyDetected(DomainEvent):
    """A wallet crossed into the smart-money class on the evidence so far."""

    aggregate_type: str = "wallet"
    address: str
    smart_money_score: float


class FundingRelationshipFound(DomainEvent):
    """A funding edge between two wallets was established."""

    aggregate_type: str = "wallet"
    source: str
    target: str
    kind: str


class ClusterCreated(DomainEvent):
    """A coordinated-wallet cluster was identified."""

    aggregate_type: str = "cluster"
    cluster: Cluster
    token: TokenRef


class WalletProfileComputed(DomainEvent):
    """A full wallet profile was (re)computed — carries the snapshot."""

    aggregate_type: str = "wallet"
    address: str
    profile: WalletProfile


class WalletIntelligenceComputed(DomainEvent):
    """Wallet-side intelligence finished for a token; the snapshot is ready."""

    aggregate_type: str = "token"
    token: TokenRef
    snapshot: IntelligenceSnapshot

"""Wallet-intelligence value objects."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from hades.contexts.common.domain.value_objects import Score, WalletAddress
from hades.shared_kernel.domain.base import ValueObject


class WalletReputation(StrEnum):
    SMART_MONEY = "smart_money"
    NEUTRAL = "neutral"
    SUSPICIOUS = "suspicious"
    KNOWN_SCAMMER = "known_scammer"


class WalletProfile(ValueObject):
    """A profiled wallet relevant to a token (deployer or notable holder)."""

    address: WalletAddress
    reputation: WalletReputation
    prior_token_count: int = 0
    prior_rug_count: int = 0
    role: str = "holder"  # e.g. "deployer", "early_buyer", "holder"


class WalletAssessment(ValueObject):
    """Aggregate wallet-side verdict for a token."""

    score: Score
    deployer: WalletProfile | None = None
    notable_holders: list[WalletProfile] = Field(default_factory=list)
    smart_money_count: int = 0

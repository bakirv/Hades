"""Immutable value objects shared across every context.

Each enforces its own invariants at construction so an invalid quantity can
never exist inside the domain (a ``Percentage`` is always 0–100, a
``Probability`` always 0–1, ``Money`` never has a mismatched currency in
arithmetic). Contexts pass these inside events; nobody re-validates downstream.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import Field, field_validator, model_validator

from hades.shared_kernel.domain.base import ValueObject

# Solana mint addresses / wallet pubkeys are base58, 32–44 chars.
_BASE58_MIN = 32
_BASE58_MAX = 44


class TokenMint(ValueObject):
    """A Solana SPL token mint address — the canonical identity of a token."""

    address: str = Field(min_length=_BASE58_MIN, max_length=_BASE58_MAX)

    @field_validator("address")
    @classmethod
    def _no_whitespace(cls, v: str) -> str:
        if any(c.isspace() for c in v):
            raise ValueError("mint address must not contain whitespace")
        return v

    def __str__(self) -> str:
        return self.address


class WalletAddress(ValueObject):
    """A Solana wallet public key (deployer, trader, liquidity provider…)."""

    address: str = Field(min_length=_BASE58_MIN, max_length=_BASE58_MAX)

    def __str__(self) -> str:
        return self.address


class TokenRef(ValueObject):
    """Lightweight reference to a token: its mint plus optional display metadata.

    This is what the Scanner emits and what every downstream context keys on.
    Symbol/name are best-effort labels, never used for identity.
    """

    mint: TokenMint
    symbol: str | None = None
    name: str | None = None


class Money(ValueObject):
    """A monetary amount in a named currency. Default unit is USD.

    Arithmetic across currencies is rejected; use ``Decimal`` internally to
    avoid float error on financial quantities.
    """

    amount: Decimal
    currency: str = "USD"

    @field_validator("amount", mode="before")
    @classmethod
    def _coerce(cls, v: Decimal | float | int | str) -> Decimal:
        return Decimal(str(v))

    def _assert_same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise ValueError(f"currency mismatch: {self.currency} vs {other.currency}")

    def __add__(self, other: Money) -> Money:
        self._assert_same_currency(other)
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def __sub__(self, other: Money) -> Money:
        self._assert_same_currency(other)
        return Money(amount=self.amount - other.amount, currency=self.currency)


class Percentage(ValueObject):
    """A percentage in the closed range [0, 100]."""

    value: float = Field(ge=0, le=100)

    def as_fraction(self) -> float:
        return self.value / 100.0


class Probability(ValueObject):
    """A probability in [0, 1]. The Scoring Engine speaks in probabilities.

    Example: ``Probability(value=0.82)`` == "82% chance ROI > 20%". The model
    *never* returns a buy/sell decision — only calibrated probabilities.
    """

    value: float = Field(ge=0.0, le=1.0)


class Confidence(ValueObject):
    """Model confidence in [0, 1] — how much to trust the probability itself."""

    value: float = Field(ge=0.0, le=1.0)


class Score(ValueObject):
    """A normalised 0–100 score with a human-readable label bucket.

    Used for Security, Wallet and Final composite scores. Comparable so contexts
    can threshold against config (``score >= settings.scoring.min_final_score``).
    """

    value: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def _round(self) -> Score:
        object.__setattr__(self, "value", round(self.value, 2))
        return self

    @property
    def label(self) -> str:
        if self.value >= 80:
            return "excellent"
        if self.value >= 60:
            return "good"
        if self.value >= 40:
            return "fair"
        return "poor"

    def __ge__(self, other: float | Score) -> bool:
        return self.value >= (other.value if isinstance(other, Score) else other)

    def __lt__(self, other: float | Score) -> bool:
        return self.value < (other.value if isinstance(other, Score) else other)

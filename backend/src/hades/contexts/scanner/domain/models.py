"""Scanner value objects — what discovery produces before anything is judged.

None of these carry an opinion about a token. They are raw observations: the
metadata we could gather, a pool we saw, a data-quality issue we detected. The
Scanner's whole job is to fill these in as completely and cleanly as possible.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import Field

from hades.contexts.common.domain.value_objects import Money, TokenMint, TokenRef
from hades.shared_kernel.domain.base import ValueObject


class TokenMetadata(ValueObject):
    """Everything the Metadata Collector could learn about a token.

    Persisted in full even when a field is not yet used downstream — the point of
    the Scanner is to accumulate knowledge. All fields are optional because
    sources vary in completeness; the Quality Validator flags what is missing.
    """

    mint: TokenMint
    name: str | None = None
    symbol: str | None = None
    decimals: int | None = None
    total_supply: Decimal | None = None
    # Off-chain / social metadata.
    logo_uri: str | None = None
    website: str | None = None
    twitter: str | None = None
    telegram: str | None = None
    discord: str | None = None
    description: str | None = None
    # On-chain program / authority facts (rug-relevant, collected not judged).
    program: str | None = None
    update_authority: str | None = None
    mint_authority: str | None = None
    freeze_authority: str | None = None
    is_mutable: bool | None = None
    created_at: datetime | None = None
    # Provenance: which providers contributed, and anything not modelled above.
    sources: tuple[str, ...] = ()
    extra: dict[str, str] = Field(default_factory=dict)

    def as_ref(self) -> TokenRef:
        return TokenRef(mint=self.mint, symbol=self.symbol, name=self.name)

    @property
    def has_socials(self) -> bool:
        return any((self.website, self.twitter, self.telegram, self.discord))


class RawPool(ValueObject):
    """A liquidity pool as seen by a DEX source, before any analysis."""

    address: str
    dex: str
    base_mint: TokenMint
    quote_mint: TokenMint | None = None
    liquidity: Money
    lp_mint: str | None = None
    created_at: datetime | None = None


class AnomalyKind(StrEnum):
    """Categories the Quality Validator classifies a bad datum into."""

    NEGATIVE_VALUE = "negative_value"
    DUPLICATE = "duplicate"
    OUTLIER = "outlier"
    INVALID_TIMESTAMP = "invalid_timestamp"
    INCOMPLETE = "incomplete"
    MALFORMED = "malformed"


class QualityIssue(ValueObject):
    """One problem the Quality Validator found in a datum (recorded, not raised).

    ``fatal`` marks issues that make the datum unusable (it is rejected); non-fatal
    issues are annotations kept for observability (e.g. missing socials).
    """

    kind: AnomalyKind
    field: str
    detail: str
    fatal: bool = False


class ValidationOutcome(ValueObject):
    """The result of validating a datum: whether it is accepted + any issues."""

    accepted: bool
    issues: tuple[QualityIssue, ...] = ()

    @property
    def fatal_issues(self) -> tuple[QualityIssue, ...]:
        return tuple(i for i in self.issues if i.fatal)

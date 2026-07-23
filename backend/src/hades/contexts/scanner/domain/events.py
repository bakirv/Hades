"""Domain events emitted by the Scanner context.

Every stage of acquisition produces a past-tense fact. Downstream contexts react
to these; the Scanner itself never calls anyone. ``TokenDiscovered`` is event #1
of a token's life in the system; the rest enrich the record or report on the
health of the acquisition machinery itself.
"""

from __future__ import annotations

from hades.contexts.common.domain.value_objects import Money, TokenRef
from hades.contexts.scanner.domain.models import AnomalyKind, RawPool, TokenMetadata
from hades.shared_kernel.domain.events import DomainEvent


class TokenDiscovered(DomainEvent):
    """A new candidate token passed coarse gating and entered the pipeline.

    This is event #1 of every trade's lifecycle. Downstream contexts key their
    work off ``token`` and correlate the whole decision via ``correlation_id``.
    """

    aggregate_type: str = "token"
    token: TokenRef
    source: str  # which scanner source surfaced it (e.g. "pumpfun")
    initial_liquidity: Money
    discovered_from_signature: str | None = None  # on-chain tx if applicable


class PoolDiscovered(DomainEvent):
    """A new liquidity pool / market was observed for a token."""

    aggregate_type: str = "token"
    token: TokenRef
    pool: RawPool
    source: str


class TokenMetadataCollected(DomainEvent):
    """The Metadata Collector finished gathering a token's metadata."""

    aggregate_type: str = "token"
    token: TokenRef
    metadata: TokenMetadata


class SignificantChangeDetected(DomainEvent):
    """A meaningful change to an already-known token (e.g. a liquidity jump)."""

    aggregate_type: str = "token"
    token: TokenRef
    metric: str
    previous: float
    current: float


class RpcEndpointSwitched(DomainEvent):
    """The RPC Manager promoted a different provider to active."""

    aggregate_type: str = "rpc"
    previous: str | None
    current: str
    reason: str


class SourceHealthChanged(DomainEvent):
    """A discovery source went down or recovered (a DEX adapter's availability)."""

    aggregate_type: str = "source"
    source: str
    available: bool
    detail: str = ""


class DataQualityAnomalyDetected(DomainEvent):
    """The Quality Validator rejected or flagged a datum. Recorded, never fatal."""

    aggregate_type: str = "token"
    subject: str  # mint address or pool/source identifier
    kind: AnomalyKind
    field: str
    detail: str

"""Domain events emitted by the Security Engine.

Everything the engine does leaves a trace on the bus. Downstream contexts react
to :class:`TokenApproved` (only approved tokens continue to scoring); operators
and the dashboard react to the granular risk events; the audit log records them
all. The engine never decides a trade — these are facts about *analysis*, not
orders.
"""

from __future__ import annotations

from hades.contexts.common.domain.value_objects import TokenRef
from hades.contexts.security.domain.models import SecurityAssessment
from hades.shared_kernel.domain.events import DomainEvent


class SecurityAnalysisStarted(DomainEvent):
    """Analysis of a token's security has begun."""

    aggregate_type: str = "token"
    token: TokenRef


class SecurityScoreComputed(DomainEvent):
    """A token's security risk has been assessed (approved or not)."""

    aggregate_type: str = "token"
    token: TokenRef
    assessment: SecurityAssessment
    vetoed: bool  # true if a critical flag hard-blocks the token


class TokenApproved(DomainEvent):
    """A token cleared the Security Engine and may proceed to scoring."""

    aggregate_type: str = "token"
    token: TokenRef
    score: float


class TokenRejected(DomainEvent):
    """A token failed the Security Engine and will never reach the AI Committee."""

    aggregate_type: str = "token"
    token: TokenRef
    score: float
    reasons: tuple[str, ...] = ()


class ContractRiskDetected(DomainEvent):
    """A contract/authority red flag was found (mint/freeze/upgrade authority…)."""

    aggregate_type: str = "token"
    token: TokenRef
    code: str
    severity: str
    detail: str


class LiquidityWarning(DomainEvent):
    """A liquidity/LP concern was found (unlocked LP, thin pool, extraction)."""

    aggregate_type: str = "token"
    token: TokenRef
    code: str
    detail: str


class ClusterFound(DomainEvent):
    """A wallet cluster (likely single entity behind many wallets) was detected."""

    aggregate_type: str = "token"
    token: TokenRef
    member_count: int
    pct_supply: float
    funder: str | None = None


class DeveloperRisk(DomainEvent):
    """The token's developer carries reputational risk (prior rugs / scammer)."""

    aggregate_type: str = "wallet"
    token: TokenRef
    deployer: str
    detail: str

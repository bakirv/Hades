"""Ports defined by the Risk Manager.

Following Dependency Inversion, the Risk Manager depends only on the narrow
abstractions here, never on concrete infrastructure. The Portfolio context
supplies the read model (:class:`PortfolioReadPort`); infrastructure supplies the
durable stores and the upstream-facts assembler. Individual rules implement
:class:`RiskPolicy` and the manager runs them as a chain - any rule may veto,
approval requires all to pass.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from hades.contexts.learning.domain.events import CommitteePredictionGenerated
from hades.contexts.risk.domain.models import (
    PolicyOutcome,
    PortfolioRiskState,
    RiskAssessment,
    RiskCandidate,
    RiskControlState,
)


@runtime_checkable
class PortfolioReadPort(Protocol):
    """The portfolio read model the Risk Manager evaluates against.

    Owned by the Portfolio context; the Risk Manager depends only on this
    interface (Interface Segregation), never on the Portfolio internals. Returns
    a fully-assembled, immutable snapshot so the policy chain stays pure.
    """

    async def risk_state(self) -> PortfolioRiskState: ...


@runtime_checkable
class RiskPolicy(Protocol):
    """A single composable risk rule. The manager runs them as a chain.

    Rules are *pure*: they read the pre-assembled candidate and portfolio state
    and return a verdict, doing no I/O. ``proposed_notional_usd`` is the size the
    Position Sizing Engine intends to open (0 for pre-sizing quality rules), so
    allocation rules can check "does adding this breach a cap?".
    """

    @property
    def name(self) -> str: ...

    def evaluate(
        self,
        candidate: RiskCandidate,
        state: PortfolioRiskState,
        proposed_notional_usd: float,
    ) -> PolicyOutcome: ...


@runtime_checkable
class RiskStateStore(Protocol):
    """Durable persistence of the defence-layer control state.

    The Kill Switch level, Circuit Breaker and Emergency Mode must survive a
    restart - a halt is not cleared by redeploying. Implementations upsert a
    single latest control-state row.
    """

    async def load(self) -> RiskControlState | None: ...

    async def save(self, state: RiskControlState) -> None: ...


@runtime_checkable
class RiskAuditStore(Protocol):
    """Append-only record of every risk decision, for audit and learning."""

    async def record(self, assessment: RiskAssessment) -> None: ...

    async def recent(self, limit: int = 50) -> tuple[RiskAssessment, ...]: ...


@runtime_checkable
class RiskContextBuilder(Protocol):
    """Assembles a :class:`RiskCandidate` from a committee prediction event.

    Infrastructure implements this: it reads the committee's probabilities and
    joins the upstream security/wallet/liquidity facts (degrading to neutral when
    absent). The Risk Manager depends only on this abstraction.
    """

    async def build(self, event: CommitteePredictionGenerated) -> RiskCandidate: ...


@runtime_checkable
class RiskFactsPort(Protocol):
    """Assembles upstream facts about a token needed to build a candidate.

    Reads the latest security verdict, developer reputation, wallet-risk and
    liquidity for a token. Every read degrades to a neutral default when absent
    (missing data lowers conviction / raises doubt, it is never an error).
    """

    async def facts_for(self, mint: str) -> dict[str, float | bool | str | None]: ...

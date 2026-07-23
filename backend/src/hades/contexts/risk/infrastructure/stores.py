"""Persistence adapters for the Risk Manager - in-memory + PostgreSQL.

Two stores: the append-only decision audit (:class:`RiskAuditStore`) and the
durable defence-layer control state (:class:`RiskStateStore`). The audit keeps
the full :class:`RiskAssessment` as JSONB so any committed trade is fully
traceable; the control state persists the single latest posture so a halt is not
cleared by a restart. In-memory variants back tests and single-process runs.
"""

from __future__ import annotations

from collections import deque
from decimal import Decimal

from sqlalchemy import desc, select

from hades.contexts.risk.domain.models import RiskAssessment, RiskControlState
from hades.shared_kernel.persistence.database import Database
from hades.shared_kernel.persistence.models.risk import (
    RiskControlStateRecord,
    RiskDecisionRecord,
)

_CONTROL_KEY = "singleton"


# =============================================================================
# In-memory
# =============================================================================


class InMemoryRiskAuditStore:
    def __init__(self, maxlen: int = 1000) -> None:
        self._ring: deque[RiskAssessment] = deque(maxlen=maxlen)

    async def record(self, assessment: RiskAssessment) -> None:
        self._ring.append(assessment)

    async def recent(self, limit: int = 50) -> tuple[RiskAssessment, ...]:
        return tuple(list(reversed(self._ring))[:limit])


class InMemoryRiskStateStore:
    def __init__(self) -> None:
        self._state: RiskControlState | None = None

    async def load(self) -> RiskControlState | None:
        return self._state

    async def save(self, state: RiskControlState) -> None:
        self._state = state


# =============================================================================
# PostgreSQL
# =============================================================================


class PostgresRiskAuditStore:
    """Durable, append-only risk-decision audit."""

    def __init__(self, database: Database) -> None:
        self._db = database

    async def record(self, assessment: RiskAssessment) -> None:
        notional = (
            Decimal(str(assessment.sizing.notional.amount))
            if assessment.sizing is not None
            else None
        )
        async with self._db.session() as session:
            session.add(
                RiskDecisionRecord(
                    mint=str(assessment.token.mint),
                    symbol=assessment.token.symbol,
                    at=assessment.at,
                    decision=assessment.decision.value,
                    reject_reason=(
                        assessment.reject_reason.value if assessment.reject_reason else None
                    ),
                    conviction=assessment.conviction,
                    risk_amount_usd=Decimal(str(assessment.risk_amount_usd)),
                    notional_usd=notional,
                    headline=assessment.headline,
                    kill_switch_level=assessment.kill_switch_level,
                    circuit_breaker_open=assessment.circuit_breaker_open,
                    correlation_id=assessment.correlation_id,
                    assessment=assessment.model_dump(mode="json"),
                )
            )

    async def recent(self, limit: int = 50) -> tuple[RiskAssessment, ...]:
        async with self._db.session() as session:
            rows = (
                await session.scalars(
                    select(RiskDecisionRecord)
                    .order_by(desc(RiskDecisionRecord.at))
                    .limit(min(limit, 500))
                )
            ).all()
        return tuple(RiskAssessment.model_validate(r.assessment) for r in rows if r.assessment)


class PostgresRiskStateStore:
    """Upserts and loads the single durable control-state row."""

    def __init__(self, database: Database) -> None:
        self._db = database

    async def load(self) -> RiskControlState | None:
        async with self._db.session() as session:
            row = await session.scalar(
                select(RiskControlStateRecord).where(RiskControlStateRecord.key == _CONTROL_KEY)
            )
        if row is None or not row.state:
            return None
        return RiskControlState.model_validate(row.state)

    async def save(self, state: RiskControlState) -> None:
        async with self._db.session() as session:
            row = await session.scalar(
                select(RiskControlStateRecord).where(RiskControlStateRecord.key == _CONTROL_KEY)
            )
            payload = state.model_dump(mode="json")
            if row is None:
                session.add(
                    RiskControlStateRecord(
                        key=_CONTROL_KEY,
                        kill_switch_level=int(state.kill_switch.level),
                        circuit_breaker_open=state.circuit_breaker.open,
                        emergency_mode=state.emergency_mode,
                        state=payload,
                    )
                )
            else:
                row.kill_switch_level = int(state.kill_switch.level)
                row.circuit_breaker_open = state.circuit_breaker.open
                row.emergency_mode = state.emergency_mode
                row.state = payload

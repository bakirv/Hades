"""Security assessment repository — PostgreSQL + in-memory.

Persists every verdict for audit and research. Rejected tokens are stored too:
they are the most valuable training data the platform produces. Flags, positives,
explanation and per-analyzer facts are serialised as JSONB so the full,
explainable record survives without a rigid column per signal.
"""

from __future__ import annotations

from sqlalchemy import select

from hades.contexts.security.domain.models import SecurityAssessment
from hades.shared_kernel.logging import get_logger
from hades.shared_kernel.persistence.database import Database
from hades.shared_kernel.persistence.models import SecurityAssessmentRecord, Token

_logger = get_logger("security.repository")


def _serialise(assessment: SecurityAssessment) -> dict[str, object]:
    return {
        "mint": str(assessment.token.mint),
        "decision": assessment.decision.value,
        "approved": assessment.approved,
        "vetoed": assessment.has_critical_flag,
        "score": assessment.score.value,
        "sub_scores": dict(assessment.sub_scores),
        "flags": [f.model_dump(mode="json") for f in assessment.flags],
        "positives": [p.model_dump(mode="json") for p in assessment.positives],
        "explanation": (
            assessment.explanation.model_dump(mode="json") if assessment.explanation else {}
        ),
        "facts": assessment.facts,
        "duration_ms": assessment.duration_ms,
    }


class PostgresSecurityRepository:
    """PostgreSQL-backed audit + research store for assessments."""

    def __init__(self, database: Database) -> None:
        self._db = database

    async def save(self, assessment: SecurityAssessment) -> None:
        payload = _serialise(assessment)
        async with self._db.session() as session:
            token_id = await session.scalar(
                select(Token.id).where(Token.mint == str(assessment.token.mint))
            )
            session.add(
                SecurityAssessmentRecord(
                    token_id=token_id,
                    analyzed_at=assessment.analyzed_at,
                    **payload,
                )
            )


class InMemorySecurityRepository:
    """In-process assessment store for tests."""

    def __init__(self) -> None:
        self.saved: list[SecurityAssessment] = []

    async def save(self, assessment: SecurityAssessment) -> None:
        self.saved.append(assessment)

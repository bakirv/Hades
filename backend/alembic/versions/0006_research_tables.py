"""research lab tables

Adds the tables the Research Lab context owns — its permanent, append-only
memory: ``research_experiments`` (reproducible experiment results),
``research_backtests``, ``research_candidates`` (rule genomes, never code),
``research_shadows`` (virtual ledgers), ``research_promotions`` (human-gated
recommendations), ``research_reports``, ``research_knowledge`` (the Knowledge
Base) and ``research_hypotheses``. The pre-existing ``research_jobs`` /
``experiments`` / opportunity tables from the baseline are untouched.

The lab has no path to execution, so none of these tables can trade; they only
record knowledge. Built from the ORM models so the migration never drifts from
``Base.metadata``.

Revision ID: 0006_research_tables
Revises: 0005_risk_tables
Create Date: 2026-07-22
"""

from __future__ import annotations

from alembic import op

from hades.shared_kernel.persistence.models import (
    ResearchBacktestRecord,
    ResearchCandidateRecord,
    ResearchExperimentRecord,
    ResearchHypothesisRecord,
    ResearchKnowledgeRecord,
    ResearchPromotionRecord,
    ResearchReportRecord,
    ResearchShadowRecord,
)

revision = "0006_research_tables"
down_revision = "0005_risk_tables"
branch_labels = None
depends_on = None

_TABLES = (
    ResearchExperimentRecord.__table__,
    ResearchBacktestRecord.__table__,
    ResearchCandidateRecord.__table__,
    ResearchShadowRecord.__table__,
    ResearchPromotionRecord.__table__,
    ResearchReportRecord.__table__,
    ResearchKnowledgeRecord.__table__,
    ResearchHypothesisRecord.__table__,
)


def upgrade() -> None:
    bind = op.get_bind()
    for table in _TABLES:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(_TABLES):
        table.drop(bind=bind, checkfirst=True)

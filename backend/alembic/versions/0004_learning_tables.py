"""ai committee (learning) tables

Adds the tables the Learning context (the AI Committee) owns — the brain's
auditable, versioned memory: ``committee_predictions`` (every fused verdict),
``committee_models`` (the append-only Model Registry with transparent weights),
``committee_datasets``, ``committee_feature_importance``, ``committee_drift`` and
``committee_outcomes`` (the labelled learning ledger). Built from the ORM models
so it never drifts from ``Base.metadata``; existing tables are untouched.

Revision ID: 0004_learning_tables
Revises: 0003_intelligence_tables
Create Date: 2026-07-21
"""

from __future__ import annotations

from alembic import op

from hades.shared_kernel.persistence.models import (
    CommitteeDatasetRecord,
    CommitteeDriftRecord,
    CommitteeFeatureImportanceRecord,
    CommitteeModelRecord,
    CommitteeOutcomeRecord,
    CommitteePredictionRecord,
)

revision = "0004_learning_tables"
down_revision = "0003_intelligence_tables"
branch_labels = None
depends_on = None

_TABLES = (
    CommitteeModelRecord.__table__,
    CommitteeDatasetRecord.__table__,
    CommitteePredictionRecord.__table__,
    CommitteeFeatureImportanceRecord.__table__,
    CommitteeDriftRecord.__table__,
    CommitteeOutcomeRecord.__table__,
)


def upgrade() -> None:
    bind = op.get_bind()
    for table in _TABLES:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(_TABLES):
        table.drop(bind=bind, checkfirst=True)

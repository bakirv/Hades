"""risk manager (portfolio + risk) tables

Adds the two tables the Risk Manager owns - ``risk_decisions`` (the append-only
audit of every approval/rejection with its full explanation) and
``risk_control_state`` (the single durable defence-layer posture so a halt
survives a restart). The portfolio time-series tables (``portfolio_history``,
``equity_curve``, ``pnl_history``) already exist from the baseline schema and are
untouched. Built from the ORM models so it never drifts from ``Base.metadata``.

Revision ID: 0005_risk_tables
Revises: 0004_learning_tables
Create Date: 2026-07-21
"""

from __future__ import annotations

from alembic import op

from hades.shared_kernel.persistence.models import (
    RiskControlStateRecord,
    RiskDecisionRecord,
)

revision = "0005_risk_tables"
down_revision = "0004_learning_tables"
branch_labels = None
depends_on = None

_TABLES = (
    RiskDecisionRecord.__table__,
    RiskControlStateRecord.__table__,
)


def upgrade() -> None:
    bind = op.get_bind()
    for table in _TABLES:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(_TABLES):
        table.drop(bind=bind, checkfirst=True)

"""wallet intelligence tables

Adds the tables the Wallet Intelligence context owns — the permanent on-chain
knowledge base: ``wallet_profiles`` (current profile per wallet), ``wallet_history``
(append-only version log), ``wallet_timeline``, ``wallet_relationships``,
``intel_clusters`` and ``wallet_knowledge``. Built from the ORM models so it never
drifts from ``Base.metadata``; existing tables are untouched.

Revision ID: 0003_intelligence_tables
Revises: 0002_scanner_tables
Create Date: 2026-07-21
"""

from __future__ import annotations

from alembic import op

from hades.shared_kernel.persistence.models import (
    IntelClusterRecord,
    WalletHistoryRecord,
    WalletKnowledgeRecord,
    WalletProfileRecord,
    WalletRelationshipRecord,
    WalletTimelineRecord,
)

revision = "0003_intelligence_tables"
down_revision = "0002_scanner_tables"
branch_labels = None
depends_on = None

_TABLES = (
    WalletProfileRecord.__table__,
    WalletHistoryRecord.__table__,
    WalletTimelineRecord.__table__,
    WalletRelationshipRecord.__table__,
    IntelClusterRecord.__table__,
    WalletKnowledgeRecord.__table__,
)


def upgrade() -> None:
    bind = op.get_bind()
    for table in _TABLES:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(_TABLES):
        table.drop(bind=bind, checkfirst=True)

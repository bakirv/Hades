"""scanner data-acquisition tables

Phase 3 (Scanner). Adds the tables the data-acquisition subsystem owns:
``token_metadata`` (full collected metadata, one current row per token),
``data_anomalies`` (Quality Validator findings) and ``token_snapshots`` (the
History Builder's point-in-time state store). Built from the ORM models so it
never drifts from ``Base.metadata``; existing tables are untouched.

Revision ID: 0002_scanner_tables
Revises: 0001_initial_schema
Create Date: 2026-07-20
"""

from __future__ import annotations

from alembic import op

from hades.shared_kernel.persistence.models import (
    DataAnomaly,
    TokenMetadataRecord,
    TokenSnapshot,
)

revision = "0002_scanner_tables"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None

_TABLES = (
    TokenMetadataRecord.__table__,
    DataAnomaly.__table__,
    TokenSnapshot.__table__,
)


def upgrade() -> None:
    bind = op.get_bind()
    for table in _TABLES:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(_TABLES):
        table.drop(bind=bind, checkfirst=True)

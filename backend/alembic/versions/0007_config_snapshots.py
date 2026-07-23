"""config snapshots table

Adds ``config_snapshots`` — the append-only, versioned history of the platform's
non-secret configuration posture (Phase 10 Configuration Manager). Each row is a
whole redacted snapshot with a SHA-256 checksum, so configuration can be
exported, versioned, diffed and drift-checked over the platform's life. Secrets
are redacted before a payload is ever written here.

The pre-existing ``audit_log`` and ``system_configuration`` tables (baseline
schema) are reused by the Audit System and Configuration Manager and need no
change, so this migration only introduces the new snapshot table. Built from the
ORM model so the migration never drifts from ``Base.metadata``.

Revision ID: 0007_config_snapshots
Revises: 0006_research_tables
Create Date: 2026-07-22
"""

from __future__ import annotations

from alembic import op

from hades.shared_kernel.persistence.models import ConfigSnapshot

revision = "0007_config_snapshots"
down_revision = "0006_research_tables"
branch_labels = None
depends_on = None

_TABLES = (ConfigSnapshot.__table__,)


def upgrade() -> None:
    bind = op.get_bind()
    for table in _TABLES:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(_TABLES):
        table.drop(bind=bind, checkfirst=True)

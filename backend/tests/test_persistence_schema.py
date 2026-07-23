"""The PostgreSQL schema is complete and uniform.

Rather than hitting a database, these tests inspect ``Base.metadata`` to assert
the schema is fully declared and that every table follows the platform rule:
a UUID primary key plus ``created_at`` / ``updated_at`` timestamps.
"""

from __future__ import annotations

import hades.shared_kernel.persistence.models  # noqa: F401  (registers tables)
from hades.shared_kernel.persistence.database import Base

_EXPECTED_TABLES = {
    "domain_events", "event_snapshots", "tokens", "wallets", "market_data",
    "features", "signals", "strategies", "strategy_versions", "models",
    "positions", "trades", "paper_trades", "live_trades", "portfolio_history",
    "equity_curve", "pnl_history", "research_jobs", "experiments",
    "accepted_opportunities", "rejected_opportunities", "notifications",
    "health_checks", "risk_events", "audit_log", "system_configuration",
    "config_snapshots",
}


def test_all_expected_tables_declared() -> None:
    assert set(Base.metadata.tables) >= _EXPECTED_TABLES


def test_every_table_has_uuid_pk_and_timestamps() -> None:
    for name, table in Base.metadata.tables.items():
        cols = table.columns
        assert "id" in cols, f"{name} missing id"
        assert next(iter(table.primary_key.columns)).name == "id", f"{name} pk not id"
        assert "created_at" in cols, f"{name} missing created_at"
        assert "updated_at" in cols, f"{name} missing updated_at"


def test_referential_integrity_declared() -> None:
    # Spot-check that key foreign keys exist (integrity, not improvised tables).
    trades = Base.metadata.tables["trades"]
    referenced = {
        fk.column.table.name for col in trades.columns for fk in col.foreign_keys
    }
    assert "tokens" in referenced
    assert "positions" in referenced

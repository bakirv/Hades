"""The Security Engine tables are declared and follow the platform conventions."""

from __future__ import annotations

import hades.shared_kernel.persistence.models  # noqa: F401  (registers tables)
from hades.shared_kernel.persistence.database import Base

_SECURITY_TABLES = {
    "security_assessments",
    "blacklist_entries",
    "whitelist_entries",
    "developer_reputation",
    "wallet_clusters",
}


def test_security_tables_declared() -> None:
    assert set(Base.metadata.tables) >= _SECURITY_TABLES


def test_security_tables_have_uuid_pk_and_timestamps() -> None:
    for name in _SECURITY_TABLES:
        cols = Base.metadata.tables[name].columns
        assert "id" in cols
        assert "created_at" in cols
        assert "updated_at" in cols


def test_assessments_reference_tokens() -> None:
    table = Base.metadata.tables["security_assessments"]
    referenced = {
        fk.column.table.name for col in table.columns for fk in col.foreign_keys
    }
    assert "tokens" in referenced

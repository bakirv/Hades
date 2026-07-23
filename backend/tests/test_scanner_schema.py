"""The Phase-3 scanner tables are declared and reference tokens correctly."""

from __future__ import annotations

import hades.shared_kernel.persistence.models  # noqa: F401  (registers tables)
from hades.shared_kernel.persistence.database import Base

_SCANNER_TABLES = {"token_metadata", "data_anomalies", "token_snapshots"}


def test_scanner_tables_declared() -> None:
    assert set(Base.metadata.tables) >= _SCANNER_TABLES


def test_scanner_tables_have_uuid_pk_and_timestamps() -> None:
    for name in _SCANNER_TABLES:
        cols = Base.metadata.tables[name].columns
        assert "id" in cols
        assert "created_at" in cols
        assert "updated_at" in cols


def test_metadata_and_snapshots_reference_tokens() -> None:
    for name in ("token_metadata", "token_snapshots"):
        table = Base.metadata.tables[name]
        referenced = {
            fk.column.table.name for col in table.columns for fk in col.foreign_keys
        }
        assert "tokens" in referenced

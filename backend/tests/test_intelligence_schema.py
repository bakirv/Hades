"""The Wallet Intelligence tables are declared and follow platform conventions."""

from __future__ import annotations

import hades.shared_kernel.persistence.models  # noqa: F401  (registers tables)
from hades.shared_kernel.persistence.database import Base

_INTEL_TABLES = {
    "wallet_profiles",
    "wallet_history",
    "wallet_timeline",
    "wallet_relationships",
    "intel_clusters",
    "wallet_knowledge",
}


def test_intelligence_tables_declared() -> None:
    assert set(Base.metadata.tables) >= _INTEL_TABLES


def test_intelligence_tables_have_uuid_pk_and_timestamps() -> None:
    for name in _INTEL_TABLES:
        cols = Base.metadata.tables[name].columns
        assert "id" in cols
        assert "created_at" in cols
        assert "updated_at" in cols

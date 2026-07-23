"""The Configuration Manager redacts secrets, versions, diffs and imports."""

from __future__ import annotations

import pytest

from hades.contexts.audit.application.recorder import AuditRecorder
from hades.contexts.audit.infrastructure.store import InMemoryAuditStore
from hades.ops.config_manager import (
    REDACTED,
    ConfigManager,
    InMemoryConfigSnapshotStore,
    InMemoryRuntimeConfigStore,
    checksum,
    diff,
    redact,
)
from hades.shared_kernel.config import get_settings


def _manager() -> ConfigManager:
    return ConfigManager(
        get_settings(),
        snapshots=InMemoryConfigSnapshotStore(),
        runtime=InMemoryRuntimeConfigStore(),
        audit=AuditRecorder(InMemoryAuditStore()),
    )


def test_redact_blanks_secret_leaves() -> None:
    data = {"password": "hunter2", "host": "db", "nested": {"api_key": "abc", "port": 5432}}
    out = redact(data)
    assert out["password"] == REDACTED
    assert out["host"] == "db"
    assert out["nested"]["api_key"] == REDACTED
    assert out["nested"]["port"] == 5432


async def test_export_never_leaks_secrets() -> None:
    export = await _manager().export()
    settings = export["settings"]
    assert settings["postgres"]["password"] == REDACTED
    # Non-secret values survive untouched.
    assert settings["postgres"]["host"]
    assert settings["trading_mode"] == "paper"


async def test_snapshot_versions_and_get() -> None:
    manager = _manager()
    first = await manager.snapshot(actor="tester")
    second = await manager.snapshot(actor="tester")
    assert first["version"] == 1
    assert second["version"] == 2
    versions = await manager.list_versions()
    assert len(versions) == 2
    full = await manager.get_version(1)
    assert full is not None and "payload" in full


def test_diff_reports_changes() -> None:
    before = {"a": 1, "b": {"c": 2}}
    after = {"a": 1, "b": {"c": 3, "d": 4}}
    delta = diff(before, after)
    assert delta["changed"]["b.c"] == {"from": 2, "to": 3}
    assert delta["added"]["b.d"] == 4
    assert delta["removed"] == {}


async def test_drift_detection() -> None:
    manager = _manager()
    await manager.snapshot(actor="tester")
    drift_clean = await manager.detect_drift()
    assert drift_clean["drifted"] is False

    # A runtime override changes the live posture → drift from the last snapshot.
    await manager.import_config(
        {"settings": {}, "runtime": {"feature_flag": "x"}}, actor="tester"
    )
    drift_after = await manager.detect_drift()
    assert drift_after["drifted"] is True


async def test_import_refuses_reserved_keys() -> None:
    manager = _manager()
    result = await manager.import_config(
        {"settings": {}, "runtime": {"trading_mode": "live", "ok_key": 1}}, actor="attacker"
    )
    assert "trading_mode" in result["refused"]
    assert "ok_key" in result["applied"]


async def test_import_rejects_invalid_payload() -> None:
    with pytest.raises(ValueError):
        await _manager().import_config({"no_settings": True}, actor="tester")


def test_checksum_is_stable_and_order_independent() -> None:
    assert checksum({"a": 1, "b": 2}) == checksum({"b": 2, "a": 1})
    assert checksum({"a": 1}) != checksum({"a": 2})

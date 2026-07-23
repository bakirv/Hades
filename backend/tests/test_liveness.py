"""Liveness heartbeat files back the background-service healthchecks."""

from __future__ import annotations

from pathlib import Path

from hades.ops.liveness import Liveness


def test_touch_makes_file_fresh(tmp_path: Path) -> None:
    liveness = Liveness("worker", directory=str(tmp_path))
    assert liveness.age_seconds() is None  # not written yet
    assert liveness.is_fresh(60) is False

    liveness.touch()
    assert liveness.path.exists()
    assert liveness.is_fresh(60) is True
    age = liveness.age_seconds()
    assert age is not None and age < 5


def test_missing_file_is_not_fresh(tmp_path: Path) -> None:
    assert Liveness("engine", directory=str(tmp_path)).is_fresh(10) is False

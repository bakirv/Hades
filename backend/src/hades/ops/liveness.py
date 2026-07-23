"""Liveness heartbeat files for background services.

The API answers an HTTP ``/health`` probe, but the background processes (worker,
engine, watchdog, scheduler, notification) have no HTTP surface. Each instead
periodically *touches* a liveness file; Docker's healthcheck for that service
runs :mod:`hades.ops.healthcheck` which verifies the file is fresh. If a loop
hangs, the file goes stale and Docker restarts the container.
"""

from __future__ import annotations

import time
from pathlib import Path

from hades.shared_kernel.logging import get_logger

_logger = get_logger("healthcheck")


class Liveness:
    """Writes/reads a per-role liveness file (``<dir>/<role>.alive``)."""

    def __init__(self, role: str, *, directory: str = "/var/run/hades") -> None:
        self._role = role
        self._dir = Path(directory)
        self._path = self._dir / f"{role}.alive"

    @property
    def path(self) -> Path:
        return self._path

    def touch(self) -> None:
        """Record 'alive now'. Best-effort — never crash the caller."""
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            self._path.write_text(str(time.time()), encoding="utf-8")
        except OSError as exc:
            _logger.warning("liveness_touch_failed", role=self._role, error=str(exc))

    def age_seconds(self) -> float | None:
        """Seconds since the last touch, or None if the file is missing."""
        try:
            return time.time() - self._path.stat().st_mtime
        except OSError:
            return None

    def is_fresh(self, max_age_seconds: float) -> bool:
        age = self.age_seconds()
        return age is not None and age <= max_age_seconds

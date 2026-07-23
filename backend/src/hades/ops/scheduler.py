"""Scheduler process — periodic platform jobs.

Owns time-driven maintenance work: automatic backups and retention cleanup in
Phase 2 (model retraining and dataset assembly plug in here in later phases).
Each job is an interval-driven coroutine supervised by the process; a job
failure is logged and the loop continues (one bad run never stops the schedule).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from hades.ops.backups import BackupManager
from hades.ops.service import ServiceProcess
from hades.shared_kernel.logging import get_logger

_logger = get_logger("scheduler")

Job = Callable[[], Awaitable[object]]


@dataclass
class PeriodicJob:
    name: str
    interval_seconds: float
    run: Job


class Scheduler(ServiceProcess):
    """Runs registered periodic jobs on their own intervals."""

    role = "scheduler"

    async def setup(self) -> None:
        settings = self._container.settings
        if not settings.scheduler.enabled:
            self._log.info("scheduler_disabled")
            return

        jobs: list[PeriodicJob] = []
        if settings.backup.enabled:
            backup_manager = BackupManager(settings)
            jobs.append(
                PeriodicJob(
                    name="backup",
                    interval_seconds=settings.scheduler.backup_interval_hours * 3600,
                    run=lambda: asyncio.to_thread(backup_manager.create),
                )
            )
            jobs.append(
                PeriodicJob(
                    name="backup_cleanup",
                    interval_seconds=settings.scheduler.cleanup_interval_hours * 3600,
                    run=lambda: asyncio.to_thread(backup_manager.prune),
                )
            )

        for job in jobs:
            self._tasks.append(asyncio.create_task(self._run_job(job)))
        self._log.info("scheduler_ready", jobs=[j.name for j in jobs])

    async def _run_job(self, job: PeriodicJob) -> None:
        # Wait one interval before the first run so startup is not a thundering herd.
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=job.interval_seconds)
                return  # stop requested
            except TimeoutError:
                pass
            try:
                _logger.info("job_started", job=job.name)
                await job.run()
                _logger.info("job_completed", job=job.name)
            except Exception as exc:  # a job failure must not kill the loop
                _logger.error("job_failed", job=job.name, error=str(exc))

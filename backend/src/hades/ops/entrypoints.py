"""Console entrypoints referenced by ``pyproject.toml`` / docker-compose.

- ``hades-api``          → serve the FastAPI app with uvicorn.
- ``hades-worker``       → general background worker.
- ``hades-engine``       → decision-engine process (skeleton in Phase 2).
- ``hades-watchdog``     → monitoring / health watchdog.
- ``hades-scheduler``    → periodic jobs (backups, cleanup).
- ``hades-notification`` → Discord notification service.
- ``hades-backup``       → run one backup now (also usable for restore tooling).
- ``hades-preflight``    → validate config/connectivity/schema; non-zero on failure.

Keeping process launching here (not scattered ``__main__`` blocks) means the
Dockerfile command and local invocation share one definition.
"""

from __future__ import annotations

import asyncio
import sys

import uvicorn

from hades.shared_kernel.config import get_settings


def run_api() -> None:
    """Serve the REST API. Accepts an optional ``--reload`` flag for dev."""
    settings = get_settings()
    reload = "--reload" in sys.argv
    uvicorn.run(
        "hades.api.app:create_app",
        factory=True,
        host=settings.api.host,
        port=settings.api.port,
        workers=1 if reload else settings.api.workers,
        reload=reload,
        log_config=None,  # we own logging via structlog
    )


def run_worker() -> None:
    from hades.ops.worker import Worker

    asyncio.run(Worker().run())


def run_engine() -> None:
    from hades.ops.engine import Engine

    asyncio.run(Engine().run())


def run_watchdog() -> None:
    from hades.ops.watchdog import WatchdogProcess

    asyncio.run(WatchdogProcess().run())


def run_scheduler() -> None:
    from hades.ops.scheduler import Scheduler

    asyncio.run(Scheduler().run())


def run_notification() -> None:
    from hades.ops.notification import NotificationProcess

    asyncio.run(NotificationProcess().run())


def run_backup() -> None:
    """Create one backup immediately (used by cron/manual invocation)."""
    from hades.ops.backups import BackupManager

    manager = BackupManager(get_settings())
    archive = manager.create()
    sys.stdout.write(f"backup created: {archive}\n")


def run_preflight() -> None:
    """Validate configuration, connectivity and schema; exit non-zero on failure."""
    from hades.ops.preflight import run_preflight as _run_preflight

    _run_preflight()

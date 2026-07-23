"""Backup & restore manager.

Produces timestamped, restorable backups of everything that matters and cannot
be regenerated: the PostgreSQL database (``pg_dump`` custom format), plus the
config, models, research, docs and (optionally) critical logs directories. Old
backups are pruned to a configurable retention count.

Runs on a schedule (the Scheduler) and on demand (``hades-backup``). ``pg_dump`` /
``pg_restore`` ship in the backend image (``postgresql-client``).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
from datetime import UTC, datetime
from pathlib import Path

from hades.shared_kernel.config import Settings
from hades.shared_kernel.logging import get_logger

_logger = get_logger("backup")


class BackupManager:
    """Creates, prunes and restores platform backups."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._backup_dir = Path(settings.backup.directory)

    # --- create ---------------------------------------------------------------
    def create(self) -> Path:
        """Create one backup archive and return its path."""
        cfg = self._settings.backup
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        staging = self._backup_dir / f"staging-{timestamp}"
        staging.mkdir(parents=True, exist_ok=True)
        _logger.info("backup_started", timestamp=timestamp)

        try:
            if cfg.include_database:
                self._dump_database(staging / "database.dump")
            if cfg.include_config:
                self._copy_dir(Path(self._settings.paths.config), staging / "config")
            if cfg.include_models:
                self._copy_dir(Path(self._settings.paths.models), staging / "models")
            if cfg.include_research:
                self._copy_dir(Path(self._settings.paths.research), staging / "research")
            if cfg.include_docs:
                self._copy_dir(Path(self._settings.paths.docs), staging / "docs")
            if cfg.include_logs:
                self._copy_dir(Path(self._settings.paths.logs), staging / "logs")

            archive = self._backup_dir / f"hades-backup-{timestamp}.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                tar.add(staging, arcname=f"hades-backup-{timestamp}")
        finally:
            shutil.rmtree(staging, ignore_errors=True)

        _logger.info("backup_completed", archive=str(archive), size_bytes=archive.stat().st_size)
        self.prune()
        return archive

    def _dump_database(self, target: Path) -> None:
        pg = self._settings.postgres
        env = {**os.environ, "PGPASSWORD": pg.password}
        cmd = [
            "pg_dump",
            "-h",
            pg.host,
            "-p",
            str(pg.port),
            "-U",
            pg.user,
            "-d",
            pg.db,
            "-F",
            "c",  # custom format → restorable with pg_restore
            "-f",
            str(target),
        ]
        _logger.info("pg_dump_started", db=pg.db)
        subprocess.run(cmd, env=env, check=True, capture_output=True)

    @staticmethod
    def _copy_dir(source: Path, target: Path) -> None:
        if source.exists():
            shutil.copytree(source, target, dirs_exist_ok=True)

    # --- retention ------------------------------------------------------------
    def prune(self) -> None:
        keep = self._settings.backup.retention_count
        archives = sorted(
            self._backup_dir.glob("hades-backup-*.tar.gz"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for stale in archives[keep:]:
            stale.unlink(missing_ok=True)
            _logger.info("backup_pruned", archive=str(stale))

    def list_backups(self) -> list[Path]:
        return sorted(
            self._backup_dir.glob("hades-backup-*.tar.gz"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

    # --- restore --------------------------------------------------------------
    def restore(self, archive: Path, *, restore_database: bool = True) -> None:
        """Restore an archive. Database restore uses ``pg_restore --clean``."""
        _logger.warning("restore_started", archive=str(archive))
        extract_dir = self._backup_dir / "restore-tmp"
        shutil.rmtree(extract_dir, ignore_errors=True)
        extract_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(extract_dir, filter="data")

        root = next(extract_dir.iterdir())
        if restore_database and (root / "database.dump").exists():
            self._restore_database(root / "database.dump")
        for name, dest in (
            ("config", self._settings.paths.config),
            ("models", self._settings.paths.models),
            ("research", self._settings.paths.research),
            ("docs", self._settings.paths.docs),
        ):
            source = root / name
            if source.exists():
                self._copy_dir(source, Path(dest))

        shutil.rmtree(extract_dir, ignore_errors=True)
        _logger.warning("restore_completed", archive=str(archive))

    def _restore_database(self, dump: Path) -> None:
        pg = self._settings.postgres
        env = {**os.environ, "PGPASSWORD": pg.password}
        cmd = [
            "pg_restore",
            "-h",
            pg.host,
            "-p",
            str(pg.port),
            "-U",
            pg.user,
            "-d",
            pg.db,
            "--clean",
            "--if-exists",
            "--no-owner",
            str(dump),
        ]
        _logger.warning("pg_restore_started", db=pg.db)
        subprocess.run(cmd, env=env, check=True, capture_output=True)

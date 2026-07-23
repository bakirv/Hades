"""ClickHouse provider — analytical read model (prepared, not required).

CQRS separates the write path (PostgreSQL, this repo's operational store) from a
heavy analytical read path. ClickHouse is that read path for time-series
analytics, backtesting and research. It is optional in Phase 2: the client
dependency (``clickhouse-connect``) is an opt-in extra, so this module imports it
lazily and degrades gracefully when the analytics layer is not installed/enabled.
"""

from __future__ import annotations

from typing import Any

from hades.shared_kernel.config.settings import ClickHouseSettings
from hades.shared_kernel.errors import ConfigurationError
from hades.shared_kernel.logging import get_logger

_logger = get_logger("analytics.clickhouse")


class ClickHouseProvider:
    """Lazily-connected ClickHouse client wrapper.

    Nothing connects until :meth:`client` is first called, and only if enabled,
    so the core image (without the ``analytics`` extra) never imports the driver.
    """

    def __init__(self, settings: ClickHouseSettings) -> None:
        self._settings = settings
        self._client: Any | None = None

    @property
    def enabled(self) -> bool:
        return self._settings.enabled

    def client(self) -> Any:
        if not self._settings.enabled:
            raise ConfigurationError("ClickHouse is disabled (CLICKHOUSE_ENABLED=false)")
        if self._client is None:
            try:
                import clickhouse_connect  # type: ignore[import-not-found]
            except ImportError as exc:  # pragma: no cover - optional dependency
                raise ConfigurationError(
                    "clickhouse-connect not installed; install the 'analytics' extra"
                ) from exc
            self._client = clickhouse_connect.get_client(
                host=self._settings.host,
                port=self._settings.port,
                database=self._settings.db,
                username=self._settings.user,
                password=self._settings.password,
            )
            _logger.info("clickhouse_connected", host=self._settings.host)
        return self._client

    async def ping(self) -> bool:
        if not self._settings.enabled:
            return True  # disabled ≠ unhealthy
        try:
            return bool(self.client().ping())
        except Exception as exc:  # probe must never raise
            _logger.warning("clickhouse_ping_failed", error=str(exc))
            return False

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

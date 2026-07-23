"""Analytical read-model integration (ClickHouse) — prepared, opt-in.

ClickHouse backs analytics / backtesting / research time-series in later phases.
The architecture supports it now; the service only runs behind the ``analytics``
Docker profile and ``CLICKHOUSE_ENABLED``.
"""

from hades.shared_kernel.analytics.clickhouse import ClickHouseProvider

__all__ = ["ClickHouseProvider"]

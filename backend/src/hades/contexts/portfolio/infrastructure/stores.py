"""Persistence adapters for the portfolio time series - in-memory + PostgreSQL.

The Portfolio Manager writes its history here: a full snapshot on each recompute
(``portfolio_history``), the raw equity samples behind the chart
(``equity_curve``) and a realised/unrealised PnL log (``pnl_history``). Writes
are append-only and best-effort - a history hiccup never blocks the manager from
keeping live state. The in-memory adapter backs tests and single-process runs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from hades.contexts.portfolio.domain.models import PortfolioState
from hades.shared_kernel.persistence.database import Database
from hades.shared_kernel.persistence.models.portfolio import (
    EquityCurve,
    PnLHistory,
    PortfolioHistory,
)


def _dec(value: float) -> Decimal:
    return Decimal(str(round(value, 18)))


class InMemoryPortfolioHistoryStore:
    """Bounded in-process history - keeps recent snapshots/equity/PnL for tests."""

    def __init__(self) -> None:
        self.snapshots: list[PortfolioState] = []
        self.equity: list[float] = []
        self.pnl: list[tuple[str, float]] = []

    async def record_snapshot(self, state: PortfolioState, *, mode: str) -> None:
        self.snapshots.append(state)

    async def record_equity(self, equity_usd: float, *, mode: str) -> None:
        self.equity.append(equity_usd)

    async def record_pnl(
        self, amount_usd: float, *, kind: str, mode: str, mint: str | None = None
    ) -> None:
        self.pnl.append((kind, amount_usd))


class PostgresPortfolioHistoryStore:
    """Durable, append-only portfolio history in PostgreSQL."""

    def __init__(self, database: Database) -> None:
        self._db = database

    async def record_snapshot(self, state: PortfolioState, *, mode: str) -> None:
        async with self._db.session() as session:
            session.add(
                PortfolioHistory(
                    mode=mode,
                    snapshot_at=state.at,
                    total_equity_usd=_dec(state.equity_usd),
                    cash_usd=_dec(state.cash_usd),
                    positions_value_usd=_dec(state.invested_usd),
                    open_positions=state.open_positions,
                    exposure_pct=_dec(state.exposure_pct),
                    realized_pnl_usd=_dec(state.realized_pnl_usd),
                    unrealized_pnl_usd=_dec(state.unrealized_pnl_usd),
                    details={"roi_pct": state.roi_pct, "drawdown_pct": state.drawdown_pct},
                )
            )

    async def record_equity(self, equity_usd: float, *, mode: str) -> None:
        async with self._db.session() as session:
            session.add(
                EquityCurve(mode=mode, timestamp=datetime.now(UTC), equity_usd=_dec(equity_usd))
            )

    async def record_pnl(
        self, amount_usd: float, *, kind: str, mode: str, mint: str | None = None
    ) -> None:
        async with self._db.session() as session:
            session.add(
                PnLHistory(
                    mode=mode,
                    kind=kind,
                    amount_usd=_dec(amount_usd),
                    timestamp=datetime.now(UTC),
                )
            )

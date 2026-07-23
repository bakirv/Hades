"""Portfolio Prometheus metrics - one declaration site for the context.

Surfaces the live book: equity, cash, invested capital, exposure, realised /
unrealised PnL, open-position count and drawdown. Gauges (not counters) because
these are point-in-time levels the Portfolio Manager sets on each recompute.
"""

from __future__ import annotations

from hades.shared_kernel.observability import MetricsRegistry


class PortfolioMetrics:
    """Typed accessors over the shared metrics registry for the portfolio."""

    def __init__(self, metrics: MetricsRegistry) -> None:
        self.equity_usd = metrics.gauge(
            "hades_portfolio_equity_usd", "Total portfolio equity (USD)"
        )
        self.cash_usd = metrics.gauge("hades_portfolio_cash_usd", "Uninvested cash (USD)")
        self.invested_usd = metrics.gauge(
            "hades_portfolio_invested_usd", "Capital in open positions (USD)"
        )
        self.exposure_pct = metrics.gauge(
            "hades_portfolio_exposure_pct", "Invested capital as a percentage of equity"
        )
        self.realized_pnl_usd = metrics.gauge(
            "hades_portfolio_realized_pnl_usd", "Cumulative realised PnL (USD)"
        )
        self.unrealized_pnl_usd = metrics.gauge(
            "hades_portfolio_unrealized_pnl_usd", "Marked unrealised PnL (USD)"
        )
        self.open_positions = metrics.gauge(
            "hades_portfolio_open_positions", "Number of open positions"
        )
        self.drawdown_pct = metrics.gauge(
            "hades_portfolio_drawdown_pct", "Peak-to-trough drawdown (percent)"
        )

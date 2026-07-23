"""Exposure Engine - measures and caps concentration along every axis.

Meme-coin risk is concentration risk: too much in one token, one developer, one
narrative, one wallet cluster, or one market regime turns many "independent"
bets into a single one. This engine aggregates the open book along each
:class:`ExposureAxis` (as a percentage of equity) and answers the only question
the policy chain needs: *would opening this candidate at this size breach a
cap?* Pure and deterministic - no I/O, no state.
"""

from __future__ import annotations

from hades.contexts.risk.domain.models import (
    ExposureAxis,
    ExposureBreakdown,
    ExposureLimits,
    OpenPositionView,
    PortfolioRiskState,
    RiskCandidate,
)


class ExposureBreach:
    """A single breached exposure cap (a tiny named tuple-like carrier)."""

    __slots__ = ("axis", "exposure_pct", "key", "limit_pct")

    def __init__(self, axis: ExposureAxis, key: str, exposure_pct: float, limit_pct: float) -> None:
        self.axis = axis
        self.key = key
        self.exposure_pct = exposure_pct
        self.limit_pct = limit_pct


def _axis_key(position: OpenPositionView, axis: ExposureAxis) -> str | None:
    if axis is ExposureAxis.TOKEN:
        return str(position.token.mint)
    if axis is ExposureAxis.DEVELOPER:
        return position.developer
    if axis is ExposureAxis.CLUSTER:
        return position.cluster
    if axis is ExposureAxis.STRATEGY:
        return position.strategy
    if axis is ExposureAxis.NARRATIVE:
        return position.narrative
    if axis is ExposureAxis.REGIME:
        return position.regime
    return None


def _candidate_key(candidate: RiskCandidate, axis: ExposureAxis) -> str | None:
    if axis is ExposureAxis.TOKEN:
        return str(candidate.token.mint)
    if axis is ExposureAxis.DEVELOPER:
        return candidate.developer
    if axis is ExposureAxis.CLUSTER:
        return candidate.cluster
    if axis is ExposureAxis.STRATEGY:
        return candidate.strategy
    if axis is ExposureAxis.NARRATIVE:
        return candidate.narrative
    if axis is ExposureAxis.REGIME:
        return candidate.regime
    return None


class ExposureEngine:
    """Aggregates the open book by axis and checks caps against candidates."""

    def __init__(self, limits: ExposureLimits) -> None:
        self._limits = limits

    def breakdown(self, state: PortfolioRiskState, axis: ExposureAxis) -> ExposureBreakdown:
        """Current exposure along ``axis`` as a percentage of equity, per key."""
        equity = state.capital.equity_usd
        by_key: dict[str, float] = {}
        if equity <= 0:
            return ExposureBreakdown(axis=axis, by_key=by_key)
        for pos in state.open_positions:
            key = _axis_key(pos, axis)
            if key is None:
                continue
            by_key[key] = round(by_key.get(key, 0.0) + pos.notional_usd / equity * 100.0, 4)
        return ExposureBreakdown(axis=axis, by_key=by_key)

    def total_exposure_pct(self, state: PortfolioRiskState) -> float:
        equity = state.capital.equity_usd
        if equity <= 0:
            return 0.0
        invested = sum(p.notional_usd for p in state.open_positions)
        return round(invested / equity * 100.0, 4)

    def _limit_for(self, axis: ExposureAxis) -> float:
        return {
            ExposureAxis.TOKEN: self._limits.per_token_pct,
            ExposureAxis.DEVELOPER: self._limits.per_developer_pct,
            ExposureAxis.CLUSTER: self._limits.per_cluster_pct,
            ExposureAxis.STRATEGY: self._limits.per_strategy_pct,
            ExposureAxis.NARRATIVE: self._limits.per_narrative_pct,
            ExposureAxis.REGIME: self._limits.per_regime_pct,
        }.get(axis, 100.0)

    def check(
        self,
        candidate: RiskCandidate,
        state: PortfolioRiskState,
        proposed_notional_usd: float,
    ) -> ExposureBreach | None:
        """Return the first axis the candidate would over-concentrate, or None.

        Checks the total-portfolio cap first, then each per-axis cap. The
        prospective exposure adds ``proposed_notional_usd`` to the axis key the
        candidate belongs to.
        """
        equity = state.capital.equity_usd
        if equity <= 0 or proposed_notional_usd <= 0:
            return None
        add_pct = proposed_notional_usd / equity * 100.0

        for axis in (
            ExposureAxis.TOKEN,
            ExposureAxis.DEVELOPER,
            ExposureAxis.CLUSTER,
            ExposureAxis.STRATEGY,
            ExposureAxis.NARRATIVE,
            ExposureAxis.REGIME,
        ):
            key = _candidate_key(candidate, axis)
            if key is None:
                continue
            current = self.breakdown(state, axis).pct_for(key)
            after = round(current + add_pct, 4)
            limit = self._limit_for(axis)
            if after > limit:
                return ExposureBreach(axis, key, after, limit)
        return None

"""Shared analyzer scaffolding — flag helpers and sub-score computation.

Every analyzer turns observations into a list of :class:`RiskFlag` /
:class:`PositiveSignal` and lets :func:`build_report` derive the numeric
sub-score. Centralising the score formula keeps analyzers focused on *detection*
(what is wrong) rather than *arithmetic* (how much to subtract), and guarantees a
single, auditable severity → penalty mapping across the whole engine.
"""

from __future__ import annotations

from collections.abc import Sequence

from hades.contexts.common.domain.value_objects import Score
from hades.contexts.security.domain.models import (
    AnalyzerReport,
    PositiveSignal,
    RiskFlag,
    RiskSeverity,
)

#: How many points each flag severity subtracts from a 100-point sub-score. A
#: CRITICAL flag is handled separately: it floors the sub-score at 0 (and the
#: engine hard-vetoes the token).
_SEVERITY_PENALTY: dict[RiskSeverity, float] = {
    RiskSeverity.INFO: 0.0,
    RiskSeverity.LOW: 8.0,
    RiskSeverity.MEDIUM: 20.0,
    RiskSeverity.HIGH: 40.0,
    RiskSeverity.CRITICAL: 100.0,
}

#: Each positive signal earns back a few points, capped so reassurances can never
#: outweigh a real concern (safety is a floor, not something you can buy back).
_POSITIVE_BONUS = 6.0
_POSITIVE_CAP = 18.0


def flag(code: str, severity: RiskSeverity, detail: str) -> RiskFlag:
    return RiskFlag(code=code, severity=severity, detail=detail)


def positive(code: str, detail: str) -> PositiveSignal:
    return PositiveSignal(code=code, detail=detail)


def score_from(
    flags: Sequence[RiskFlag],
    positives: Sequence[PositiveSignal],
    *,
    base: float = 100.0,
) -> float:
    """Derive a 0-100 sub-score from flags and positives.

    Any CRITICAL flag floors the score at 0. Otherwise deductions accumulate and
    a bounded positive bonus is added back, clamped to [0, 100].
    """
    if any(f.is_critical for f in flags):
        return 0.0
    penalty = sum(_SEVERITY_PENALTY[f.severity] for f in flags)
    bonus = min(_POSITIVE_CAP, _POSITIVE_BONUS * len(positives))
    return max(0.0, min(100.0, base - penalty + bonus))


def build_report(
    name: str,
    *,
    flags: Sequence[RiskFlag] = (),
    positives: Sequence[PositiveSignal] = (),
    facts: dict[str, object] | None = None,
    insufficient_data: bool = False,
    base: float = 100.0,
) -> AnalyzerReport:
    """Assemble an :class:`AnalyzerReport` with its derived sub-score."""
    value = score_from(flags, positives, base=base)
    return AnalyzerReport(
        name=name,
        score=Score(value=round(value, 2)),
        flags=tuple(flags),
        positives=tuple(positives),
        facts=facts or {},
        insufficient_data=insufficient_data,
    )

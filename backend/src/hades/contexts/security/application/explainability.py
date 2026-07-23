"""Explainability Engine — every verdict must be legible.

The engine never answers merely "approved" or "rejected". For every token it
produces a human-readable account: the positives that helped, the negatives that
hurt (ordered by severity), and a one-line summary. This is what the dashboard
shows, what the audit log stores, and what a human uses to trust — or challenge —
the machine.
"""

from __future__ import annotations

from collections.abc import Sequence

from hades.contexts.security.domain.models import (
    Explanation,
    PositiveSignal,
    RiskFlag,
    RiskSeverity,
    SecurityDecision,
)

# Severity ordering for presenting the most important negatives first.
_SEVERITY_RANK: dict[RiskSeverity, int] = {
    RiskSeverity.CRITICAL: 0,
    RiskSeverity.HIGH: 1,
    RiskSeverity.MEDIUM: 2,
    RiskSeverity.LOW: 3,
    RiskSeverity.INFO: 4,
}


def build_explanation(
    *,
    decision: SecurityDecision,
    final_score: float,
    flags: Sequence[RiskFlag],
    positives: Sequence[PositiveSignal],
    reject_reasons: Sequence[str],
    max_items: int = 8,
) -> Explanation:
    """Assemble the ordered positive/negative reasons and a summary line."""
    ordered_flags = sorted(
        (f for f in flags if f.severity is not RiskSeverity.INFO),
        key=lambda f: _SEVERITY_RANK[f.severity],
    )
    negatives = tuple(f"[{f.severity.value.upper()}] {f.detail}" for f in ordered_flags[:max_items])
    positive_lines = tuple(p.detail for p in positives[:max_items])

    if decision is SecurityDecision.APPROVED:
        summary = (
            f"APPROVED with security score {final_score:.0f}/100 — "
            f"{len(positive_lines)} positive signal(s), no blocking risk."
        )
    else:
        headline = reject_reasons[0] if reject_reasons else "risk threshold not met"
        summary = (
            f"REJECTED (score {final_score:.0f}/100) — {headline}. "
            f"{len(ordered_flags)} risk flag(s) found."
        )

    return Explanation(summary=summary, positives=positive_lines, negatives=negatives)

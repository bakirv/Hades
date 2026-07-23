"""Auto Research Scheduler — decides *when* recurring research work is due.

A small, pure clock helper: given configurable intervals for each recurring task
(backtests, strategy/model comparisons, walk-forward validations, feature
discovery, report generation) it reports which tasks are due at a given time and
records that they ran. The runtime owns the actual execution loop; keeping the
"is it due?" logic here makes it trivially testable and free of I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ResearchTask(StrEnum):
    BACKTEST = "backtest"
    WALK_FORWARD = "walk_forward"
    FEATURE_DISCOVERY = "feature_discovery"
    STRATEGY_COMPARISON = "strategy_comparison"
    MODEL_COMPARISON = "model_comparison"
    DAILY_REPORT = "daily_report"
    WEEKLY_REPORT = "weekly_report"
    MONTHLY_REPORT = "monthly_report"


_DEFAULT_INTERVALS: dict[ResearchTask, float] = {
    ResearchTask.BACKTEST: 6 * 3600.0,
    ResearchTask.WALK_FORWARD: 12 * 3600.0,
    ResearchTask.FEATURE_DISCOVERY: 24 * 3600.0,
    ResearchTask.STRATEGY_COMPARISON: 6 * 3600.0,
    ResearchTask.MODEL_COMPARISON: 12 * 3600.0,
    ResearchTask.DAILY_REPORT: 24 * 3600.0,
    ResearchTask.WEEKLY_REPORT: 7 * 24 * 3600.0,
    ResearchTask.MONTHLY_REPORT: 30 * 24 * 3600.0,
}


@dataclass
class AutoResearchScheduler:
    """Tracks per-task intervals and last-run times to report what's due."""

    intervals: dict[ResearchTask, float] = field(default_factory=lambda: dict(_DEFAULT_INTERVALS))
    _last_run: dict[ResearchTask, float] = field(default_factory=dict)

    def due(self, now: float) -> tuple[ResearchTask, ...]:
        """Tasks whose interval has elapsed since they last ran (or never ran)."""
        out: list[ResearchTask] = []
        for task, interval in self.intervals.items():
            last = self._last_run.get(task)
            if last is None or (now - last) >= interval:
                out.append(task)
        return tuple(out)

    def mark_ran(self, task: ResearchTask, now: float) -> None:
        self._last_run[task] = now

    def seed(self, now: float, *, tasks: tuple[ResearchTask, ...] | None = None) -> None:
        """Mark tasks as just-run so they are not all due immediately at startup."""
        for task in tasks or tuple(self.intervals):
            self._last_run[task] = now

"""ShadowLifecycle - governs the Research -> ... -> Production promotion ladder.

Every new strategy climbs the ladder one rung at a time: Research -> Backtest ->
Replay -> Paper -> Shadow -> Production. Stages are never skipped and a promotion is
never automatic - this component only *validates and records* a requested
transition, emitting the corresponding facts. Anything below Production runs in
shadow: its signals are recorded and evaluated but excluded from the production
ensemble.
"""

from __future__ import annotations

from hades.contexts.strategy.application.base import BaseStrategy
from hades.contexts.strategy.domain.models import LIFECYCLE_ORDER, LifecycleStage


class PromotionError(ValueError):
    """Raised when a requested lifecycle transition is illegal (e.g. a skip)."""


class ShadowLifecycle:
    """Validates and applies single-step lifecycle transitions on a strategy."""

    @staticmethod
    def stage_index(stage: LifecycleStage) -> int:
        return LIFECYCLE_ORDER.index(stage)

    @staticmethod
    def is_shadow(stage: LifecycleStage) -> bool:
        """Everything below Production is shadow (recorded, not ensembled)."""
        return stage is not LifecycleStage.PRODUCTION

    def next_stage(self, stage: LifecycleStage) -> LifecycleStage | None:
        idx = self.stage_index(stage)
        if idx + 1 >= len(LIFECYCLE_ORDER):
            return None
        return LIFECYCLE_ORDER[idx + 1]

    def promote(self, strategy: BaseStrategy) -> tuple[LifecycleStage, LifecycleStage]:
        """Advance a strategy exactly one rung. Returns ``(previous, new)``."""
        current = strategy.metadata.lifecycle_stage
        nxt = self.next_stage(current)
        if nxt is None:
            raise PromotionError(f"{strategy.name} is already at {current.value}")
        strategy.override_metadata(lifecycle_stage=nxt)
        return current, nxt

    def set_stage(
        self, strategy: BaseStrategy, target: LifecycleStage
    ) -> tuple[LifecycleStage, LifecycleStage]:
        """Move to an *adjacent* stage (up or down one rung). Skips are rejected."""
        current = strategy.metadata.lifecycle_stage
        if abs(self.stage_index(target) - self.stage_index(current)) != 1:
            raise PromotionError(
                f"illegal transition {current.value} -> {target.value} (one step only)"
            )
        strategy.override_metadata(lifecycle_stage=target)
        return current, target

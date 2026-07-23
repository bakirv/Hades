"""Model Registry service — append-only, versioned, human-gated promotion.

Thin application service over the :class:`ModelRegistry` port that enforces the
platform's rules and emits the lifecycle events. It never overwrites a model,
never promotes automatically, and never lets a rejected candidate slip through.
The flow is: register (trained) → validate → propose promotion → (human/policy)
promote. Promotion archives the previous active version; nothing is deleted.
"""

from __future__ import annotations

from collections.abc import Sequence

from hades.contexts.learning.application.metrics import LearningMetrics
from hades.contexts.learning.domain.events import (
    ModelPromoted,
    ModelPromotionProposed,
    ModelRejected,
    ModelTrained,
    ModelValidated,
)
from hades.contexts.learning.domain.models import (
    ModelCard,
    ModelStatus,
    ValidationReport,
)
from hades.contexts.learning.domain.ports import ModelRegistry
from hades.shared_kernel.domain.identifiers import new_id
from hades.shared_kernel.events import EventBus
from hades.shared_kernel.logging import get_logger

_logger = get_logger("committee.registry")


class ModelRegistryService:
    """Registers, validates, proposes and (on approval) promotes models."""

    def __init__(
        self, registry: ModelRegistry, event_bus: EventBus, metrics: LearningMetrics
    ) -> None:
        self._registry = registry
        self._bus = event_bus
        self._metrics = metrics

    async def register(self, card: ModelCard) -> None:
        """Append a freshly-trained candidate to the registry (never overwrites)."""
        await self._registry.register(card)
        self._metrics.models_registered.inc()
        await self._bus.publish(
            ModelTrained(
                aggregate_id=new_id(),
                model_id=card.model_id,
                name=card.name,
                model_version=card.version,
                trained_on_samples=card.trained_on_samples,
                metrics=card.metrics.as_dict(),
            )
        )

    async def register_all(self, cards: Sequence[ModelCard]) -> None:
        for card in cards:
            await self.register(card)

    async def record_validation(self, card: ModelCard, report: ValidationReport) -> None:
        """Mark a candidate validated or rejected and emit the matching event."""
        if report.passed:
            await self._registry.set_status(card.model_id, ModelStatus.VALIDATED.value)
            await self._bus.publish(
                ModelValidated(aggregate_id=new_id(), model_id=card.model_id, report=report)
            )
        else:
            await self._registry.set_status(card.model_id, ModelStatus.REJECTED.value)
            self._metrics.models_rejected.inc()
            await self._bus.publish(
                ModelRejected(aggregate_id=new_id(), model_id=card.model_id, reasons=report.reasons)
            )

    async def propose_promotion(self, card: ModelCard, report: ValidationReport) -> None:
        """Propose replacing the active model — requires human/policy approval."""
        incumbent = await self._registry.active(card.name)
        await self._bus.publish(
            ModelPromotionProposed(
                aggregate_id=new_id(),
                candidate_model_id=card.model_id,
                incumbent_model_id=incumbent.model_id if incumbent else None,
                improvement=report.improvement,
            )
        )
        _logger.info(
            "model_promotion_proposed",
            candidate=card.model_id,
            name=card.name,
            incumbent=incumbent.model_id if incumbent else None,
        )

    async def promote(self, model_id: str) -> ModelCard | None:
        """Activate a model (the human/policy-gated step). Archives the prior one."""
        card = await self._registry.get(model_id)
        if card is None:
            _logger.warning("promote_unknown_model", model_id=model_id)
            return None
        if card.status is ModelStatus.REJECTED:
            _logger.warning("promote_rejected_model_blocked", model_id=model_id)
            return None
        incumbent = await self._registry.active(card.name)
        promoted = await self._registry.promote(model_id)
        if promoted is None:
            return None
        self._metrics.models_promoted.inc()
        await self._bus.publish(
            ModelPromoted(
                aggregate_id=new_id(),
                model_id=promoted.model_id,
                name=promoted.name,
                model_version=promoted.version,
                superseded_model_id=(
                    incumbent.model_id if incumbent and incumbent.model_id != model_id else None
                ),
            )
        )
        _logger.info("model_promoted", model_id=model_id, name=promoted.name)
        return promoted

"""AI Committee runtime composition — wires and runs the brain.

Process-level wiring (the ops layer may import application + infrastructure). It
assembles the whole committee subsystem from the container and subscribes it to
the end of the analytical pipeline:

    intelligence ─WalletIntelligenceComputed─► [context builder → committee]
        ─► InferenceCompleted / CommitteeFinished / ConfidenceCalculated /
           PredictionGenerated / CommitteePredictionGenerated

It also wires Knowledge Feedback (learning from security rejections), an optional
**shadow committee** for comparison, and — when ``auto_train`` is on — a periodic,
off-the-hot-path training pass that builds *candidate* models (never promotes;
promotion stays human/policy-gated). Nothing here trades, sizes or enables live.
It only produces probabilities and evidence, and publishes a Redis status snapshot
for the dashboard.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from hades.bootstrap import Container
from hades.contexts.features.infrastructure.feature_store import (
    CachingFeatureStore,
    InMemoryFeatureStore,
    PostgresFeatureStore,
)
from hades.contexts.learning.application.committee.factory import (
    committee_from_cards,
    default_committee,
)
from hades.contexts.learning.application.committee.manager import (
    Committee,
    CommitteeManager,
    QualitySignals,
)
from hades.contexts.learning.application.confidence import ConfidenceEngine
from hades.contexts.learning.application.dataset_builder import DatasetBuilder
from hades.contexts.learning.application.explainability import ExplanationBuilder
from hades.contexts.learning.application.feature_catalog import FeatureCatalog, FeatureNormalizer
from hades.contexts.learning.application.knowledge_feedback import KnowledgeFeedback
from hades.contexts.learning.application.metrics import LearningMetrics
from hades.contexts.learning.application.regime import MarketRegimeClassifier
from hades.contexts.learning.application.registry import ModelRegistryService
from hades.contexts.learning.application.subscriber import CommitteeHandler
from hades.contexts.learning.application.training import TrainingEngine
from hades.contexts.learning.application.validation import ValidationEngine
from hades.contexts.learning.domain.events import CommitteePredictionGenerated
from hades.contexts.learning.domain.models import META_MODEL_NAME
from hades.contexts.learning.domain.ports import (
    DatasetStore,
    ModelRegistry,
    OutcomeStore,
    PredictionStore,
)
from hades.contexts.learning.infrastructure.context_builder import DecisionContextBuilder
from hades.contexts.learning.infrastructure.model_registry import (
    InMemoryModelRegistry,
    PostgresModelRegistry,
)
from hades.contexts.learning.infrastructure.stores import (
    InMemoryDatasetStore,
    InMemoryOutcomeStore,
    InMemoryPredictionStore,
    PostgresDatasetStore,
    PostgresOutcomeStore,
    PostgresPredictionStore,
)
from hades.shared_kernel.cache import CacheService
from hades.shared_kernel.domain.events import DomainEvent
from hades.shared_kernel.logging import get_logger

_logger = get_logger("committee.runtime")

#: Redis namespace + key the Worker publishes live committee status under.
COMMITTEE_STATUS_NAMESPACE = "committee"
COMMITTEE_STATUS_KEY = "status"
_STATUS_INTERVAL_SECONDS = 5.0
_STATUS_TTL_SECONDS = 30


class CommitteeRuntime:
    """Owns the wired AI Committee subsystem and its lifecycle."""

    def __init__(self, container: Container) -> None:
        self._c = container
        self._stop = asyncio.Event()
        self._metrics = LearningMetrics(container.metrics)
        self._status_cache = CacheService(container.redis, namespace=COMMITTEE_STATUS_NAMESPACE)
        self._catalog = FeatureCatalog()
        self._normalizer = FeatureNormalizer(self._catalog)
        self._feature_store = self._build_feature_store()
        self._registry: ModelRegistry = self._build_registry()
        self._prediction_store: PredictionStore = self._build_prediction_store()
        self._outcome_store: OutcomeStore = self._build_outcome_store()
        self._dataset_store: DatasetStore = self._build_dataset_store()
        self._registry_service = ModelRegistryService(
            self._registry, self._c.event_bus, self._metrics
        )
        self._dataset_builder = DatasetBuilder(self._outcome_store)
        self._training = TrainingEngine()
        self._validation = ValidationEngine()
        self._manager = self._build_manager()
        self._feedback = KnowledgeFeedback(
            self._outcome_store, self._feature_store, self._normalizer
        )
        self._predictions_session = 0
        self._last: dict[str, Any] = {}
        self._register()

    # -- construction ---------------------------------------------------------

    def _build_feature_store(self) -> Any:
        if self._c.database is not None:
            return CachingFeatureStore(PostgresFeatureStore(self._c.database), self._c.redis)
        return InMemoryFeatureStore()

    def _build_registry(self) -> ModelRegistry:
        if self._c.database is not None:
            return PostgresModelRegistry(self._c.database)
        return InMemoryModelRegistry()

    def _build_prediction_store(self) -> PredictionStore:
        if self._c.database is not None:
            return PostgresPredictionStore(self._c.database)
        return InMemoryPredictionStore()

    def _build_outcome_store(self) -> OutcomeStore:
        if self._c.database is not None:
            return PostgresOutcomeStore(self._c.database)
        return InMemoryOutcomeStore()

    def _build_dataset_store(self) -> DatasetStore:
        if self._c.database is not None:
            return PostgresDatasetStore(self._c.database)
        return InMemoryDatasetStore()

    def _build_manager(self) -> CommitteeManager:
        learning = self._c.settings.learning
        shadows: tuple[Committee, ...] = ()
        if learning.shadow_enabled:
            shadows = (default_committee(label=learning.shadow_label),)
        quality = QualitySignals(
            dataset_quality=learning.default_dataset_quality,
            sample_support=learning.default_sample_support,
        )
        return CommitteeManager(
            active=default_committee(),
            regime=MarketRegimeClassifier(),
            confidence=ConfidenceEngine(),
            explainer=ExplanationBuilder(),
            event_bus=self._c.event_bus,
            metrics=self._metrics,
            prediction_store=self._prediction_store,
            shadows=shadows,
            quality=quality,
        )

    def _register(self) -> None:
        builder = DecisionContextBuilder(self._feature_store, self._normalizer, self._c.database)
        CommitteeHandler(self._manager, builder).register(self._c.event_bus)
        self._feedback.register(self._c.event_bus)
        self._c.event_bus.subscribe(CommitteePredictionGenerated.__name__, self._on_prediction)

    # -- loading the active committee from the registry -----------------------

    async def _load_active_committee(self) -> None:
        try:
            active_cards = await self._registry.list_active()
        except Exception as exc:  # a cold registry must not stop startup
            _logger.warning("committee_registry_load_failed", error=str(exc))
            return
        if active_cards:
            self._manager.set_active(committee_from_cards(active_cards))
            _logger.info("committee_loaded_from_registry", models=len(active_cards))

    # -- scheduled training (candidates only; never promotes) -----------------

    async def train_once(self) -> None:
        """Build a dataset, train + validate candidates, register + propose.

        Runs off the hot path. It only *proposes* — promotion stays human-gated.
        """
        outcomes = await self._outcome_store.count()
        if outcomes < self._c.settings.learning.min_outcomes_to_train:
            _logger.info("training_deferred", outcomes=outcomes)
            return
        dataset = await self._dataset_builder.build()
        await self._dataset_store.save(dataset)
        version = await self._registry.next_version(META_MODEL_NAME)
        result = self._training.train(dataset, version=version)
        self._metrics.training_runs.inc()
        for card in result.cards:
            await self._registry_service.register(card)
            incumbent = await self._registry.active(card.name)
            report = self._validation.validate(
                card, dataset, incumbent=incumbent.metrics if incumbent else None
            )
            await self._registry_service.record_validation(card, report)
            if report.passed:
                await self._registry_service.propose_promotion(card, report)
        _logger.info("training_pass_complete", candidates=len(result.cards), version=version)

    async def _training_loop(self) -> None:
        interval = max(1, self._c.settings.learning.retrain_interval_hours) * 3600
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except TimeoutError:
                try:
                    await self.train_once()
                except Exception as exc:  # training must never crash the worker
                    self._metrics.errors.inc()
                    _logger.warning("scheduled_training_failed", error=str(exc))

    # -- dashboard stats ------------------------------------------------------

    async def _on_prediction(self, event: DomainEvent) -> None:
        if not isinstance(event, CommitteePredictionGenerated):
            return
        self._predictions_session += 1
        p = event.prediction
        self._last = {
            "mint": str(p.token.mint),
            "prob_roi_positive": p.meta.prob_roi_positive,
            "prob_hit_tp": p.meta.prob_hit_tp,
            "prob_hit_sl": p.meta.prob_hit_sl,
            "confidence": p.confidence.final,
            "regime": p.regime.regime.value,
            "headline": p.explanation.headline if p.explanation else "",
            "at": p.at.isoformat(),
        }

    def snapshot(self) -> dict[str, Any]:
        """Live status for the dashboard (probabilities only — never trade info)."""
        return {
            "enabled": self._c.settings.learning.committee_enabled,
            "members": len(default_committee().specialists),
            "shadow_enabled": self._c.settings.learning.shadow_enabled,
            "auto_train": self._c.settings.learning.auto_train,
            "predictions_session": self._predictions_session,
            "last_prediction": self._last,
            "updated_at": time.time(),
        }

    async def _publish_status_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self._status_cache.set(
                    COMMITTEE_STATUS_KEY, self.snapshot(), ttl_seconds=_STATUS_TTL_SECONDS
                )
            except Exception as exc:  # status publishing is best-effort
                _logger.warning("committee_status_publish_failed", error=str(exc))
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=_STATUS_INTERVAL_SECONDS)
            except TimeoutError:
                continue

    # -- lifecycle ------------------------------------------------------------

    async def start(self) -> list[asyncio.Task[None]]:
        await self._load_active_committee()
        tasks = [asyncio.create_task(self._publish_status_loop(), name="committee-status")]
        if self._c.settings.learning.auto_train:
            tasks.append(asyncio.create_task(self._training_loop(), name="committee-training"))
        _logger.info("committee_runtime_started", auto_train=self._c.settings.learning.auto_train)
        return tasks

    async def stop(self) -> None:
        self._stop.set()
        _logger.info("committee_runtime_stopped")

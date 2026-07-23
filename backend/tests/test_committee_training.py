"""Training, validation, registry, monitor, importance and feedback tests."""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

from hades.contexts.learning.application.dataset_builder import DatasetBuilder
from hades.contexts.learning.application.feature_importance import FeatureImportanceAnalyzer
from hades.contexts.learning.application.metrics import LearningMetrics
from hades.contexts.learning.application.monitor import ModelMonitor
from hades.contexts.learning.application.registry import ModelRegistryService
from hades.contexts.learning.application.training import LogisticTrainer, TrainingEngine
from hades.contexts.learning.application.validation import ValidationEngine
from hades.contexts.learning.domain.events import (
    ModelPromoted,
    ModelRejected,
    ModelTrained,
    ModelValidated,
)
from hades.contexts.learning.domain.models import (
    META_MODEL_NAME,
    Dataset,
    DriftKind,
    ModelCard,
    ModelMetrics,
    ModelStatus,
    ModelWeights,
    TrainingSample,
)
from hades.contexts.learning.infrastructure.model_registry import InMemoryModelRegistry
from hades.contexts.learning.infrastructure.stores import InMemoryOutcomeStore
from hades.shared_kernel.domain.events import DomainEvent
from hades.shared_kernel.events import InMemoryEventBus
from hades.shared_kernel.observability import MetricsRegistry


def _learnable_samples(n: int, seed: int = 7) -> list[TrainingSample]:
    """A dataset where a positive outcome genuinely depends on the features."""
    rng = random.Random(seed)
    base = datetime.now(UTC) - timedelta(days=5)
    samples: list[TrainingSample] = []
    for i in range(n):
        liq = rng.random()
        sec = rng.random()
        rug = rng.random()
        score = 1.6 * liq + 1.4 * sec - 1.2 * (1 - rug) + rng.gauss(0, 0.25)
        positive = score > 0.5
        features = {
            "basic.liquidity": liq,
            "pool.depth_usd": liq * 0.9,
            "basic.liquidity_to_mcap": liq * 0.8,
            "basic.spread_bps": 1 - liq,
            "basic.slippage_bps": 1 - liq,
            "security.score": sec,
            "security.approved": 1.0 if sec > 0.5 else 0.0,
            "security.sub.rug_pull": rug,
            "security.sub.contract": sec,
            "security.sub.developer": sec,
            "holders.gini": 1 - liq,
            "holders.top10_share_pct": 1 - liq,
            "tech.volatility": 1 - sec,
            "intel.smart_money_ratio": sec,
            "intel.avg_risk": 1 - rug,
        }
        samples.append(
            TrainingSample(
                token_mint=f"{i:044d}"[:44],
                at=base + timedelta(minutes=i),
                features=features,
                label_roi_positive=positive,
                label_hit_tp=positive,
                label_hit_sl=not positive,
                realized_roi=0.2 if positive else -0.1,
                was_executed=i % 3 != 0,
                was_rejected=i % 3 == 0,
                weight=1.0,
            )
        )
    return samples


def _dataset(n: int = 120) -> Dataset:
    samples = _learnable_samples(n)
    names = tuple(sorted({k for s in samples for k in s.features}))
    return Dataset(
        dataset_id="ds-test",
        name="test",
        created_at=datetime.now(UTC),
        samples=tuple(samples),
        feature_names=names,
    )


# --- trainer -----------------------------------------------------------------


def test_logistic_trainer_learns_signal() -> None:
    rng = random.Random(1)
    rows = []
    for _ in range(200):
        x = rng.random()
        rows.append(({"f": x}, 1 if x > 0.5 else 0, 1.0))
    weights = LogisticTrainer().fit(rows, ("f",))
    # Positive relationship -> positive coefficient.
    assert weights.coefficients["f"] > 0.5


def test_training_engine_produces_committee_and_meta() -> None:
    result = TrainingEngine().train(_dataset(), version="1")
    names = {c.name for c in result.cards}
    assert META_MODEL_NAME in names
    assert len(result.specialist_cards) == 12
    assert result.meta_card is not None
    assert result.meta_card.heads  # multi-head fusion persisted
    # A learnable dataset should give the security specialist real discrimination.
    security = next(c for c in result.specialist_cards if c.name == "security")
    assert (security.metrics.auc or 0.0) >= 0.5


def test_training_skips_small_dataset() -> None:
    result = TrainingEngine().train(_dataset(10), version="1")
    assert result.cards == []


# --- validation --------------------------------------------------------------


def test_validation_runs_full_gauntlet_and_gates() -> None:
    from hades.contexts.learning.application.validation import ValidationConfig

    dataset = _dataset(200)
    card = next(
        c for c in TrainingEngine().train(dataset, version="1").cards if c.name == "security"
    )
    report = ValidationEngine().validate(card, dataset)
    # Walk-forward + cross-validation folds ran, OOS was scored, replay computed.
    assert any(f.name.startswith("wf_") for f in report.folds)
    assert any(f.name.startswith("cv_") for f in report.folds)
    assert report.oos_metrics.samples > 0
    assert report.oos_metrics.roi is not None
    # The pass/fail verdict is exactly the conjunction of the absolute gates.
    m = report.oos_metrics
    gates_ok = (
        (m.auc or 0.0) >= 0.55 and (m.brier or 1.0) <= 0.27 and (m.calibration_error or 1.0) <= 0.15
    )
    assert report.passed == gates_ok
    # A model that clears looser gates *is* eligible (first model, no incumbent).
    loose = ValidationEngine(ValidationConfig(max_calibration_error=0.5)).validate(card, dataset)
    if (loose.oos_metrics.auc or 0.0) >= 0.55:
        assert loose.passed


def test_validation_rejects_worse_than_incumbent() -> None:
    dataset = _dataset(200)
    card = next(
        c for c in TrainingEngine().train(dataset, version="1").cards if c.name == "security"
    )
    strong_incumbent = ModelMetrics(samples=100, auc=0.99, brier=0.05, calibration_error=0.02)
    report = ValidationEngine().validate(card, dataset, incumbent=strong_incumbent)
    assert not report.passed
    assert any("incumbent" in r for r in report.reasons)


# --- registry service --------------------------------------------------------


class _Collector:
    def __init__(self, bus: InMemoryEventBus) -> None:
        self.events: list[DomainEvent] = []
        for name in (
            ModelTrained.__name__,
            ModelValidated.__name__,
            ModelRejected.__name__,
            ModelPromoted.__name__,
        ):
            bus.subscribe(name, self._collect)

    async def _collect(self, event: DomainEvent) -> None:
        self.events.append(event)

    def count(self, kind: type[DomainEvent]) -> int:
        return sum(1 for e in self.events if isinstance(e, kind))


def _card(name: str, version: str) -> ModelCard:
    return ModelCard(
        model_id=f"{name}-{version}",
        name=name,
        version=version,
        weights=ModelWeights(bias=0.0, coefficients={"f": 1.0}),
        metrics=ModelMetrics(samples=100, auc=0.7),
    )


async def test_registry_register_and_promote_flow() -> None:
    bus = InMemoryEventBus()
    collector = _Collector(bus)
    registry = InMemoryModelRegistry()
    service = ModelRegistryService(registry, bus, LearningMetrics(MetricsRegistry()))

    card = _card("security", "1")
    await service.register(card)
    assert collector.count(ModelTrained) == 1

    promoted = await service.promote(card.model_id)
    assert promoted is not None and promoted.status is ModelStatus.PROMOTED
    assert collector.count(ModelPromoted) == 1
    assert (await registry.active("security")) is not None


async def test_registry_never_overwrites_and_promotion_is_exclusive() -> None:
    registry = InMemoryModelRegistry()
    service = ModelRegistryService(registry, InMemoryEventBus(), LearningMetrics(MetricsRegistry()))
    v1, v2 = _card("security", "1"), _card("security", "2")
    await service.register(v1)
    await service.register(v2)
    await service.promote(v1.model_id)
    await service.promote(v2.model_id)
    active = await registry.active("security")
    assert active is not None and active.version == "2"
    # v1 archived, not deleted.
    versions = await registry.versions("security")
    assert {c.version for c in versions} == {"1", "2"}


async def test_rejected_model_cannot_be_promoted() -> None:
    registry = InMemoryModelRegistry()
    service = ModelRegistryService(registry, InMemoryEventBus(), LearningMetrics(MetricsRegistry()))
    card = _card("security", "1")
    await service.register(card)
    await registry.set_status(card.model_id, ModelStatus.REJECTED.value)
    assert (await service.promote(card.model_id)) is None


# --- monitor -----------------------------------------------------------------


def test_monitor_detects_feature_drift() -> None:
    monitor = ModelMonitor()
    reference = {"basic.liquidity": 0.5, "tech.volatility": 0.2}
    live = [{"basic.liquidity": 0.5, "tech.volatility": 0.9} for _ in range(40)]
    report = monitor.assess("m1", reference_means=reference, live_vectors=live)
    assert report.triggered
    assert report.kind in (DriftKind.FEATURE, DriftKind.DATA)


def test_monitor_detects_concept_drift() -> None:
    monitor = ModelMonitor()
    validated = ModelMetrics(samples=100, auc=0.75)
    live = ModelMetrics(samples=100, auc=0.60)
    report = monitor.assess(
        "m1", reference_means={}, live_vectors=[{}] * 40, validated=validated, live=live
    )
    assert report.kind is DriftKind.CONCEPT
    assert report.triggered


def test_monitor_quiet_when_stable() -> None:
    monitor = ModelMonitor()
    reference = {"basic.liquidity": 0.5}
    live = [{"basic.liquidity": 0.5} for _ in range(40)]
    assert not monitor.assess("m1", reference_means=reference, live_vectors=live).triggered


# --- feature importance ------------------------------------------------------


def test_feature_importance_flags_useless() -> None:
    card = ModelCard(
        model_id="m1",
        name="security",
        version="1",
        weights=ModelWeights(bias=0.0, coefficients={"security.score": 2.0, "dead.feature": 0.0}),
    )
    vectors = [{"security.score": 0.8, "dead.feature": 0.5} for _ in range(20)]
    importance = FeatureImportanceAnalyzer().analyze(card, vectors)
    assert "dead.feature" in importance.useless
    assert importance.importances["security.score"] > importance.importances["dead.feature"]


# --- dataset builder + outcome store -----------------------------------------


async def test_dataset_builder_includes_rejected() -> None:
    store = InMemoryOutcomeStore()
    await store.append(_learnable_samples(50))
    dataset = await DatasetBuilder(store).build()
    assert dataset.size == 50
    assert dataset.rejected_count > 0  # learns from rejected too
    assert dataset.executed_count > 0
    assert 0.0 < dataset.positive_rate < 1.0

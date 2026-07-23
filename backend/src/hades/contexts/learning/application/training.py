"""Training Engine — fit the committee's transparent models from history.

The models are linear-logistic, so training is transparent too: a small,
dependency-free gradient-descent fit with L2 regularisation produces the
per-feature coefficients. There is nothing to hide — the "trained model" is just
a new :class:`ModelWeights` (a bias and a coefficient per feature), which the
registry versions and the dashboard can diff against the previous version.

The engine trains the whole committee from one :class:`Dataset`:

    * each **specialist** is fit on *its own* feature subset to predict
      ``label_roi_positive`` — it becomes a calibrated single-facet ROI predictor;
    * the **meta-model**'s three heads are then fit on the freshly-trained
      specialists' probabilities to predict ROI / TP / SL.

It never promotes anything — it emits candidates. It is designed to run on a
worker, off the hot path, so it never blocks the live committee. Nothing here
trades or enables live.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from hades.contexts.common.domain.value_objects import TokenMint, TokenRef
from hades.contexts.learning.application.committee.base import SpecialistModel
from hades.contexts.learning.application.committee.specialists import SPECIALIST_SPECS
from hades.contexts.learning.application.mathx import (
    accuracy,
    brier_score,
    calibration_error,
    log_loss,
    precision_recall,
    roc_auc,
    sigmoid,
)
from hades.contexts.learning.application.meta_model import HIT_SL, HIT_TP, ROI_POSITIVE
from hades.contexts.learning.domain.models import (
    META_MODEL_NAME,
    CommitteeMember,
    Dataset,
    ModelCard,
    ModelMetrics,
    ModelStatus,
    ModelWeights,
    NormalizedVector,
    TrainingSample,
)
from hades.shared_kernel.domain.identifiers import new_id
from hades.shared_kernel.logging import get_logger

_logger = get_logger("committee.training")

# A placeholder token used only to satisfy the pure specialist API during meta
# training (the specialists never look at the mint — only at the feature values).
_ANY_TOKEN = TokenRef(mint=TokenMint(address="1" * 32))


@dataclass(frozen=True)
class TrainingConfig:
    """Hyper-parameters for the logistic fit (documented, conservative defaults)."""

    epochs: int = 300
    learning_rate: float = 0.15
    l2: float = 0.002
    min_samples: int = 40


@dataclass
class TrainingResult:
    """Everything one training run produced: candidate cards for the whole committee."""

    dataset_id: str
    specialist_cards: list[ModelCard] = field(default_factory=list)
    meta_card: ModelCard | None = None

    @property
    def cards(self) -> list[ModelCard]:
        return [*self.specialist_cards, *([self.meta_card] if self.meta_card else [])]


class LogisticTrainer:
    """A tiny, transparent logistic-regression fitter (batch gradient descent)."""

    def __init__(self, config: TrainingConfig | None = None) -> None:
        self._cfg = config or TrainingConfig()

    def fit(
        self,
        rows: Sequence[tuple[dict[str, float], int, float]],
        feature_names: Sequence[str],
    ) -> ModelWeights:
        """Fit ``sigmoid(bias + Σ w·x)`` on ``(features, label, weight)`` rows."""
        features = list(feature_names)
        weights = dict.fromkeys(features, 0.0)
        bias = 0.0
        lr = self._cfg.learning_rate
        l2 = self._cfg.l2
        total_w = sum(max(1e-9, w) for _, _, w in rows) or 1.0

        for _ in range(self._cfg.epochs):
            grad_w = dict.fromkeys(features, 0.0)
            grad_b = 0.0
            for x, y, sample_w in rows:
                z = bias + sum(weights[f] * x.get(f, 0.0) for f in features)
                err = (sigmoid(z) - y) * sample_w
                for f in features:
                    grad_w[f] += err * x.get(f, 0.0)
                grad_b += err
            for f in features:
                weights[f] -= lr * (grad_w[f] / total_w + l2 * weights[f])
            bias -= lr * (grad_b / total_w)

        return ModelWeights(
            bias=round(bias, 6), coefficients={f: round(weights[f], 6) for f in features}
        )


class TrainingEngine:
    """Trains the full committee (specialists + meta) from a dataset."""

    def __init__(self, config: TrainingConfig | None = None) -> None:
        self._cfg = config or TrainingConfig()
        self._trainer = LogisticTrainer(self._cfg)

    def train(self, dataset: Dataset, *, version: str = "1") -> TrainingResult:
        result = TrainingResult(dataset_id=dataset.dataset_id)
        if dataset.size < self._cfg.min_samples:
            _logger.info(
                "training_skipped_small_dataset", size=dataset.size, need=self._cfg.min_samples
            )
            return result

        samples = list(dataset.samples)
        specialists: list[SpecialistModel] = []
        for member, spec in SPECIALIST_SPECS.items():
            names = tuple(spec.default_weights.keys())
            card = self._train_specialist(member, names, samples, dataset, version)
            result.specialist_cards.append(card)
            specialists.append(SpecialistModel(spec, card.weights, version=version))

        result.meta_card = self._train_meta(specialists, samples, dataset, version)
        return result

    # -- specialists ----------------------------------------------------------

    def _train_specialist(
        self,
        member: CommitteeMember,
        names: tuple[str, ...],
        samples: Sequence[TrainingSample],
        dataset: Dataset,
        version: str,
    ) -> ModelCard:
        rows = [(s.features, int(s.label_roi_positive), s.weight) for s in samples]
        train_rows, test_rows = _split(rows)
        weights = self._trainer.fit(train_rows, names)
        metrics = _evaluate(weights, test_rows, names)
        return ModelCard(
            model_id=new_id(),
            name=member.value,
            version=version,
            kind="logistic",
            dataset_id=dataset.dataset_id,
            feature_names=names,
            weights=weights,
            metrics=metrics,
            status=ModelStatus.TRAINED,
            trained_on_samples=len(train_rows),
            notes=f"specialist:{member.value}",
        )

    # -- meta -----------------------------------------------------------------

    def _train_meta(
        self,
        specialists: Sequence[SpecialistModel],
        samples: Sequence[TrainingSample],
        dataset: Dataset,
        version: str,
    ) -> ModelCard:
        members = [s.member.value for s in specialists]
        rows_by_head: dict[str, list[tuple[dict[str, float], int, float]]] = {
            ROI_POSITIVE: [],
            HIT_TP: [],
            HIT_SL: [],
        }
        for sample in samples:
            member_probs = self._member_probs(specialists, sample)
            rows_by_head[ROI_POSITIVE].append(
                (member_probs, int(sample.label_roi_positive), sample.weight)
            )
            rows_by_head[HIT_TP].append((member_probs, int(sample.label_hit_tp), sample.weight))
            rows_by_head[HIT_SL].append((member_probs, int(sample.label_hit_sl), sample.weight))

        head_weights: dict[str, ModelWeights] = {}
        metrics = ModelMetrics(samples=len(samples))
        for head, rows in rows_by_head.items():
            train_rows, test_rows = _split(rows)
            weights = self._trainer.fit(train_rows, members)
            head_weights[head] = weights
            if head == ROI_POSITIVE:
                metrics = _evaluate(weights, test_rows, members)

        # The meta-model is multi-head: the ROI head is the card's primary weights
        # (for display/diff); all three heads live in ``heads`` so the registry
        # persists and reconstructs the full fusion model.
        return ModelCard(
            model_id=new_id(),
            name=META_MODEL_NAME,
            version=version,
            kind="logistic_meta",
            dataset_id=dataset.dataset_id,
            feature_names=tuple(members),
            weights=head_weights[ROI_POSITIVE],
            heads=head_weights,
            metrics=metrics,
            status=ModelStatus.TRAINED,
            trained_on_samples=len(samples),
            notes="meta:roi_positive|hit_tp|hit_sl heads",
        )

    @staticmethod
    def _member_probs(
        specialists: Sequence[SpecialistModel], sample: TrainingSample
    ) -> dict[str, float]:
        vector = NormalizedVector(
            token=_ANY_TOKEN,
            at=sample.at,
            values=dict(sample.features),
            coverage=1.0,
        )
        probs: dict[str, float] = {}
        for specialist in specialists:
            opinion = specialist.evaluate(vector)
            probs[specialist.member.value] = 0.5 if opinion.abstained else opinion.probability
        return probs


def _split(
    rows: Sequence[tuple[dict[str, float], int, float]], test_frac: float = 0.25
) -> tuple[list[tuple[dict[str, float], int, float]], list[tuple[dict[str, float], int, float]]]:
    """Chronological split (rows arrive oldest→newest) — no look-ahead."""
    rows = list(rows)
    if len(rows) < 8:
        return rows, rows
    cut = int(len(rows) * (1.0 - test_frac))
    return rows[:cut], rows[cut:]


def _evaluate(
    weights: ModelWeights, rows: Sequence[tuple[dict[str, float], int, float]], names: Sequence[str]
) -> ModelMetrics:
    if not rows:
        return ModelMetrics()
    pairs: list[tuple[float, int]] = []
    for x, y, _ in rows:
        z = weights.bias + sum(weights.coefficients.get(f, 0.0) * x.get(f, 0.0) for f in names)
        pairs.append((sigmoid(z), int(y)))
    precision, recall = precision_recall(pairs)
    return ModelMetrics(
        samples=len(pairs),
        accuracy=round(accuracy(pairs), 4),
        precision=round(precision, 4),
        recall=round(recall, 4),
        auc=round(roc_auc(pairs), 4),
        brier=round(brier_score(pairs), 4),
        calibration_error=round(calibration_error(pairs), 4),
        log_loss=round(log_loss(pairs), 4),
    )

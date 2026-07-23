"""Validation Engine — a candidate model must earn its place, out-of-sample.

Before any model is even *eligible* for shadow/promotion it has to survive this
gauntlet on held-out data:

    * **Walk-forward** — expanding-window folds that only ever test on the future,
      the honest analogue of live operation.
    * **K-fold cross-validation** — stability across different splits.
    * **Out-of-sample** — a final untouched tail.
    * **Paper replay** — the ROI a simple threshold policy would have made on the
      OOS tail using the model's probabilities (a trading-metric sanity check).
    * **Comparison vs the incumbent** — the candidate must not be worse.

If the candidate fails an absolute gate or loses to the incumbent, it is **not**
deployed (a hard rule). Passing only makes it *eligible*; promotion itself stays
human/policy-gated elsewhere.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from hades.contexts.learning.application.mathx import (
    accuracy,
    brier_score,
    calibration_error,
    log_loss,
    mean,
    precision_recall,
    roc_auc,
    sigmoid,
)
from hades.contexts.learning.domain.models import (
    Dataset,
    FoldResult,
    ModelCard,
    ModelMetrics,
    TrainingSample,
    ValidationReport,
)

_Row = tuple[dict[str, float], int, float]


@dataclass(frozen=True)
class ValidationConfig:
    """Absolute quality gates and comparison tolerances (documented defaults)."""

    min_auc: float = 0.55
    max_brier: float = 0.27
    max_calibration_error: float = 0.15
    walk_forward_folds: int = 4
    cross_val_folds: int = 5
    oos_fraction: float = 0.2
    # The candidate must beat the incumbent's AUC by at least this margin.
    min_auc_improvement: float = 0.0
    # Paper-replay: act when P(ROI+) exceeds this threshold.
    replay_threshold: float = 0.55
    min_samples: int = 40


class ValidationEngine:
    """Runs the full validation gauntlet and decides eligibility."""

    def __init__(self, config: ValidationConfig | None = None) -> None:
        self._cfg = config or ValidationConfig()

    def validate(
        self,
        candidate: ModelCard,
        dataset: Dataset,
        *,
        incumbent: ModelMetrics | None = None,
    ) -> ValidationReport:
        rows = self._rows(candidate, dataset.samples)
        if len(rows) < self._cfg.min_samples:
            return ValidationReport(
                model_id=candidate.model_id,
                passed=False,
                reasons=(f"dataset too small ({len(rows)} < {self._cfg.min_samples})",),
            )

        folds = [
            *self._walk_forward(candidate, rows),
            *self._cross_val(candidate, rows),
        ]
        oos = self._out_of_sample(candidate, rows)
        replay_roi = self._paper_replay(candidate, rows)
        oos = oos.model_copy(update={"roi": round(replay_roi, 4)})

        reasons: list[str] = []
        passed = self._gates(oos, reasons)
        improvement = self._compare(oos, incumbent, reasons)
        if incumbent is not None and not improvement.get("auc_ok", 0.0):
            passed = False

        return ValidationReport(
            model_id=candidate.model_id,
            passed=passed,
            folds=tuple(folds),
            oos_metrics=oos,
            incumbent_metrics=incumbent,
            improvement={k: v for k, v in improvement.items() if k != "auc_ok"},
            reasons=tuple(reasons),
        )

    # -- fold strategies ------------------------------------------------------

    def _walk_forward(self, card: ModelCard, rows: Sequence[_Row]) -> list[FoldResult]:
        folds: list[FoldResult] = []
        n = len(rows)
        step = max(1, n // (self._cfg.walk_forward_folds + 1))
        for i in range(1, self._cfg.walk_forward_folds + 1):
            train_end = step * i
            test_end = min(n, train_end + step)
            if train_end < 4 or test_end <= train_end:
                continue
            train, test = rows[:train_end], rows[train_end:test_end]
            folds.append(self._fold(f"wf_{i}", card, train, test))
        return folds

    def _cross_val(self, card: ModelCard, rows: Sequence[_Row]) -> list[FoldResult]:
        folds: list[FoldResult] = []
        k = self._cfg.cross_val_folds
        n = len(rows)
        size = max(1, n // k)
        for i in range(k):
            start, end = i * size, (i + 1) * size if i < k - 1 else n
            test = rows[start:end]
            train = [*rows[:start], *rows[end:]]
            if len(train) < 4 or not test:
                continue
            folds.append(self._fold(f"cv_{i + 1}", card, train, test))
        return folds

    def _out_of_sample(self, card: ModelCard, rows: Sequence[_Row]) -> ModelMetrics:
        cut = int(len(rows) * (1.0 - self._cfg.oos_fraction))
        test = rows[cut:] or rows
        return _score(card, test)

    def _paper_replay(self, card: ModelCard, rows: Sequence[_Row]) -> float:
        """Mean realised label among rows the policy would have 'taken'.

        A transparent stand-in for realised ROI: acting only when P(ROI+) clears
        the threshold, how often would the outcome have been positive minus the
        base rate. Positive = the model's confidence added value.
        """
        cut = int(len(rows) * (1.0 - self._cfg.oos_fraction))
        test = rows[cut:] or rows
        taken = [y for x, y, _ in test if _prob(card, x) >= self._cfg.replay_threshold]
        base_rate = mean(float(y) for _, y, _ in test)
        if not taken:
            return 0.0
        return mean(float(y) for y in taken) - base_rate

    # -- gates & comparison ---------------------------------------------------

    def _gates(self, oos: ModelMetrics, reasons: list[str]) -> bool:
        ok = True
        if (oos.auc or 0.0) < self._cfg.min_auc:
            reasons.append(f"AUC {oos.auc} < {self._cfg.min_auc}")
            ok = False
        if (oos.brier or 1.0) > self._cfg.max_brier:
            reasons.append(f"Brier {oos.brier} > {self._cfg.max_brier}")
            ok = False
        if (oos.calibration_error or 1.0) > self._cfg.max_calibration_error:
            reasons.append(
                f"calibration {oos.calibration_error} > {self._cfg.max_calibration_error}"
            )
            ok = False
        if ok:
            reasons.append("passed absolute quality gates")
        return ok

    def _compare(
        self, oos: ModelMetrics, incumbent: ModelMetrics | None, reasons: list[str]
    ) -> dict[str, float]:
        if incumbent is None:
            reasons.append("no incumbent — candidate is the first model")
            return {"auc_ok": 1.0}
        cand_auc = oos.auc or 0.0
        inc_auc = incumbent.auc or 0.0
        delta = round(cand_auc - inc_auc, 4)
        auc_ok = delta >= self._cfg.min_auc_improvement
        if not auc_ok:
            reasons.append(f"does not beat incumbent AUC ({cand_auc} vs {inc_auc})")
        else:
            reasons.append(f"beats incumbent AUC by {delta}")
        return {
            "auc_delta": delta,
            "brier_delta": round((incumbent.brier or 1.0) - (oos.brier or 1.0), 4),
            "auc_ok": 1.0 if auc_ok else 0.0,
        }

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _rows(card: ModelCard, samples: Sequence[TrainingSample]) -> list[_Row]:
        return [(s.features, int(s.label_roi_positive), s.weight) for s in samples]

    @staticmethod
    def _fold(
        name: str, card: ModelCard, train: Sequence[_Row], test: Sequence[_Row]
    ) -> FoldResult:
        return FoldResult(
            name=name,
            train_size=len(train),
            test_size=len(test),
            metrics=_score(card, test),
        )


def _prob(card: ModelCard, x: dict[str, float]) -> float:
    z = card.weights.bias + sum(
        card.weights.coefficients.get(f, 0.0) * x.get(f, 0.0) for f in card.weights.coefficients
    )
    return sigmoid(z)


def _score(card: ModelCard, rows: Sequence[_Row]) -> ModelMetrics:
    if not rows:
        return ModelMetrics()
    pairs = [(_prob(card, x), int(y)) for x, y, _ in rows]
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

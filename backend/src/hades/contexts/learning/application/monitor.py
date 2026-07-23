"""Model Monitor — watch a live model for silent degradation.

Continuously compares what the model sees and does *now* against the baseline it
was trained/validated on, and raises an alert when it starts to drift:

    * **Data drift** — the overall input distribution has moved (average absolute
      shift of feature means vs the reference).
    * **Feature drift** — a specific feature's mean moved a lot (named, so it can
      be investigated or pruned).
    * **Concept drift** — the feature→outcome relationship decayed: the live
      classification metrics (when realised outcomes are available) fell below the
      validated ones.

It only measures and alerts — it never retrains or promotes. The Training Engine
and the human-gated promotion path handle any response.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from hades.contexts.learning.application.mathx import mean
from hades.contexts.learning.domain.models import (
    DriftKind,
    DriftReport,
    ModelMetrics,
)


@dataclass(frozen=True)
class MonitorConfig:
    """Thresholds above which drift is flagged (documented, conservative)."""

    data_drift_threshold: float = 0.15  # avg |mean shift| over shared features
    feature_drift_threshold: float = 0.30  # per-feature mean shift
    concept_auc_drop: float = 0.07  # live AUC below validated AUC by this much
    min_live_samples: int = 30


class ModelMonitor:
    """Detects data / feature / concept drift for an active model."""

    def __init__(self, config: MonitorConfig | None = None) -> None:
        self._cfg = config or MonitorConfig()

    def assess(
        self,
        model_id: str,
        *,
        reference_means: dict[str, float],
        live_vectors: Sequence[dict[str, float]],
        validated: ModelMetrics | None = None,
        live: ModelMetrics | None = None,
    ) -> DriftReport:
        feature_drifts = self._feature_drifts(reference_means, live_vectors)
        data_severity = mean(feature_drifts.values()) if feature_drifts else 0.0
        worst = max(feature_drifts.items(), key=lambda kv: kv[1], default=("", 0.0))

        kind = DriftKind.NONE
        severity = 0.0
        detail = "no significant drift"
        triggered = False

        concept = self._concept_drop(validated, live)
        if concept is not None and concept > self._cfg.concept_auc_drop:
            kind = DriftKind.CONCEPT
            severity = min(1.0, concept / max(self._cfg.concept_auc_drop, 1e-6) * 0.5)
            detail = f"live AUC dropped {round(concept, 3)} vs validated"
            triggered = True
        elif worst[1] > self._cfg.feature_drift_threshold:
            kind = DriftKind.FEATURE
            severity = min(1.0, worst[1])
            detail = f"feature '{worst[0]}' mean shifted {round(worst[1], 3)}"
            triggered = True
        elif data_severity > self._cfg.data_drift_threshold:
            kind = DriftKind.DATA
            severity = min(1.0, data_severity)
            detail = f"input distribution shifted (avg {round(data_severity, 3)})"
            triggered = True

        if len(live_vectors) < self._cfg.min_live_samples and kind is not DriftKind.CONCEPT:
            triggered = False  # too little live data to trust a distribution alert
            detail = f"{detail} (below {self._cfg.min_live_samples} live samples)"

        return DriftReport(
            model_id=model_id,
            kind=kind,
            severity=round(severity, 4),
            triggered=triggered,
            detail=detail,
            feature_drifts={k: round(v, 4) for k, v in feature_drifts.items()},
            live_metrics=live,
        )

    # -- internals ------------------------------------------------------------

    @staticmethod
    def _feature_drifts(
        reference_means: dict[str, float], live_vectors: Sequence[dict[str, float]]
    ) -> dict[str, float]:
        if not live_vectors or not reference_means:
            return {}
        drifts: dict[str, float] = {}
        for feature, ref_mean in reference_means.items():
            live_mean = mean(v.get(feature, 0.0) for v in live_vectors)
            drifts[feature] = abs(live_mean - ref_mean)
        return drifts

    @staticmethod
    def _concept_drop(validated: ModelMetrics | None, live: ModelMetrics | None) -> float | None:
        if validated is None or live is None:
            return None
        if validated.auc is None or live.auc is None or (live.samples or 0) == 0:
            return None
        return validated.auc - live.auc

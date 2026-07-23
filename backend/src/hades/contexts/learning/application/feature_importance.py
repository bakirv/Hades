"""Feature-importance analyser — find which features actually earn their keep.

Computed continuously from a model's weights and the recent feature vectors it
scored. A feature's importance is its share of the total absolute contribution
(``|weight · mean|value||``) — the same legible quantity the explanations use.
That lets the platform reduce complexity automatically by flagging:

    * **useless** features — near-zero importance;
    * **redundant** features — highly correlated with a more-important kept one;
    * **stale** features — absent from the recent vectors the model actually saw.

It only reports; pruning is applied at the next training run.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from hades.contexts.learning.application.mathx import mean, stddev
from hades.contexts.learning.domain.models import FeatureImportance, ModelCard

_USELESS_SHARE = 0.01
_REDUNDANT_CORR = 0.92
_STALE_PRESENCE = 0.05


class FeatureImportanceAnalyzer:
    """Ranks features by contribution and flags dead weight."""

    def analyze(
        self, card: ModelCard, live_vectors: Sequence[dict[str, float]]
    ) -> FeatureImportance:
        features = list(card.weights.coefficients.keys())
        means = (
            {f: mean(v.get(f, 0.0) for v in live_vectors) for f in features} if live_vectors else {}
        )
        raw = {f: abs(card.weights.coefficients[f] * means.get(f, 0.0)) for f in features}
        total = sum(raw.values()) or 1.0
        importances = {f: round(raw[f] / total, 4) for f in features}

        useless = tuple(f for f, share in importances.items() if share < _USELESS_SHARE)
        stale = self._stale(features, live_vectors)
        redundant = self._redundant(features, importances, live_vectors)
        return FeatureImportance(
            model_id=card.model_id,
            computed_at=datetime.now(UTC),
            importances=importances,
            useless=useless,
            redundant=redundant,
            stale=stale,
        )

    @staticmethod
    def _stale(
        features: Sequence[str], live_vectors: Sequence[dict[str, float]]
    ) -> tuple[str, ...]:
        if not live_vectors:
            return ()
        n = len(live_vectors)
        stale: list[str] = []
        for f in features:
            presence = sum(1 for v in live_vectors if f in v) / n
            if presence < _STALE_PRESENCE:
                stale.append(f)
        return tuple(stale)

    def _redundant(
        self,
        features: Sequence[str],
        importances: dict[str, float],
        live_vectors: Sequence[dict[str, float]],
    ) -> tuple[str, ...]:
        if len(live_vectors) < 5 or len(features) < 2:
            return ()
        ordered = sorted(features, key=lambda f: importances.get(f, 0.0), reverse=True)
        kept: list[str] = []
        redundant: list[str] = []
        for feature in ordered:
            if any(self._corr(feature, keep, live_vectors) >= _REDUNDANT_CORR for keep in kept):
                redundant.append(feature)
            else:
                kept.append(feature)
        return tuple(redundant)

    @staticmethod
    def _corr(a: str, b: str, vectors: Sequence[dict[str, float]]) -> float:
        xs = [v.get(a, 0.0) for v in vectors]
        ys = [v.get(b, 0.0) for v in vectors]
        sx, sy = stddev(xs), stddev(ys)
        if sx < 1e-9 or sy < 1e-9:
            return 0.0
        mx, my = mean(xs), mean(ys)
        cov = mean((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
        return abs(cov / (sx * sy))

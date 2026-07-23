"""Feature Discovery Engine — proposes, never disposes.

Scans historical samples to rank each feature's usefulness (its |correlation|
with the realised forward return), flags features that look irrelevant (near-zero
importance) or redundant (highly correlated with another), and suggests promising
interaction combinations. It only ever emits :class:`FeatureProposal`s — a human
decides whether to act. The engine never removes a feature from production.

Pure Pearson correlations, no NumPy.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from hades.contexts.research.domain.models import FeatureProposal, safe_div
from hades.contexts.research.domain.ports import HistoricalSample

_LABEL = "forward_return"
_IRRELEVANT_BELOW = 0.03
_REDUNDANT_ABOVE = 0.92


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> float:
    n = len(xs)
    if n < 3:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    denom = math.sqrt(vx * vy)
    return safe_div(cov, denom) if denom else 0.0


def _feature_keys(samples: Sequence[HistoricalSample]) -> list[str]:
    keys: set[str] = set()
    for s in samples:
        keys.update(k for k, v in s.items() if k != _LABEL and isinstance(v, int | float))
    return sorted(keys)


class FeatureDiscoveryEngine:
    """Ranks features and proposes (never applies) additions/flags/combinations."""

    def analyze(self, samples: Sequence[HistoricalSample]) -> tuple[FeatureProposal, ...]:
        if len(samples) < 3 or _LABEL not in samples[0]:
            return ()
        keys = _feature_keys(samples)
        labels = [float(s.get(_LABEL, 0.0)) for s in samples]
        columns = {k: [float(s.get(k, 0.0)) for s in samples] for k in keys}

        importance = {k: abs(_pearson(columns[k], labels)) for k in keys}
        proposals: list[FeatureProposal] = []

        # Irrelevant: near-zero importance.
        for k in keys:
            if importance[k] < _IRRELEVANT_BELOW:
                proposals.append(
                    FeatureProposal(
                        feature=k,
                        action="flag_irrelevant",
                        importance=round(importance[k], 4),
                        rationale="near-zero correlation with realised return",
                    )
                )

        # Redundant: highly correlated pairs (report the weaker of the two).
        for i, a in enumerate(keys):
            for b in keys[i + 1 :]:
                corr = abs(_pearson(columns[a], columns[b]))
                if corr >= _REDUNDANT_ABOVE:
                    weaker = a if importance[a] <= importance[b] else b
                    stronger = b if weaker == a else a
                    proposals.append(
                        FeatureProposal(
                            feature=weaker,
                            action="flag_redundant",
                            importance=round(importance[weaker], 4),
                            correlation=round(corr, 4),
                            rationale=f"redundant with '{stronger}'",
                            combines=(a, b),
                        )
                    )

        # Combination: the two strongest independent features may interact.
        strong = sorted(keys, key=lambda k: importance[k], reverse=True)[:2]
        if len(strong) == 2 and all(importance[k] >= _IRRELEVANT_BELOW for k in strong):
            product = [columns[strong[0]][i] * columns[strong[1]][i] for i in range(len(samples))]
            combo_imp = abs(_pearson(product, labels))
            if combo_imp > max(importance[strong[0]], importance[strong[1]]):
                proposals.append(
                    FeatureProposal(
                        feature=f"{strong[0]}*{strong[1]}",
                        action="combine",
                        importance=round(combo_imp, 4),
                        rationale="interaction outperforms both parents",
                        combines=tuple(strong),
                    )
                )

        return tuple(proposals)

    def importance(self, samples: Sequence[HistoricalSample]) -> dict[str, float]:
        """Bare feature-importance map (|corr| with the label)."""
        if len(samples) < 3 or _LABEL not in samples[0]:
            return {}
        labels = [float(s.get(_LABEL, 0.0)) for s in samples]
        return {
            k: round(abs(_pearson([float(s.get(k, 0.0)) for s in samples], labels)), 4)
            for k in _feature_keys(samples)
        }

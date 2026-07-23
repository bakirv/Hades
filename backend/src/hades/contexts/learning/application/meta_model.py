"""The Meta Model — the chair that fuses every opinion into three probabilities.

The meta-model is the only thing that speaks for the whole committee, and even it
never says "buy". It combines the specialists' opinions into exactly three
calibrated numbers the Risk Manager can use:

    P(ROI positive) · P(hit take-profit) · P(hit stop-loss)

It is itself a transparent logistic model, one head per output. Each member's
opinion enters *centred* on 0.5 and *scaled by that member's own confidence*, so
an abstaining or unsure specialist contributes nothing rather than dragging the
fusion toward the middle. The per-head weights are documented priors (a
risk/security-heavy head for the stop, a momentum/wallet-heavy head for the
target) and can be refit by the Training Engine into a new registry version.
"""

from __future__ import annotations

from collections.abc import Sequence

from hades.contexts.common.domain.value_objects import TokenRef
from hades.contexts.learning.application.mathx import clamp, sigmoid
from hades.contexts.learning.domain.models import (
    CommitteeMember,
    MetaPrediction,
    ModelWeights,
    Opinion,
)

_M = CommitteeMember

# Head names.
ROI_POSITIVE = "roi_positive"
HIT_TP = "hit_tp"
HIT_SL = "hit_sl"


def _default_head_weights() -> dict[str, ModelWeights]:
    """Documented priors for the three fusion heads (per committee member)."""
    roi = {
        _M.SECURITY.value: 1.1,
        _M.RISK.value: 1.0,
        _M.LIQUIDITY.value: 0.9,
        _M.WALLET.value: 0.9,
        _M.MOMENTUM.value: 0.8,
        _M.MARKET_REGIME.value: 0.7,
        _M.HOLDER_DISTRIBUTION.value: 0.7,
        _M.DEVELOPER.value: 0.7,
        _M.MICROSTRUCTURE.value: 0.5,
        _M.BEHAVIOR.value: 0.5,
        _M.VOLATILITY.value: 0.4,
        _M.TIMING.value: 0.4,
    }
    tp = {
        _M.MOMENTUM.value: 1.2,
        _M.WALLET.value: 1.0,
        _M.MARKET_REGIME.value: 0.9,
        _M.TIMING.value: 0.8,
        _M.LIQUIDITY.value: 0.7,
        _M.MICROSTRUCTURE.value: 0.6,
        _M.VOLATILITY.value: 0.5,
        _M.BEHAVIOR.value: 0.4,
        _M.HOLDER_DISTRIBUTION.value: 0.4,
        _M.SECURITY.value: 0.3,
    }
    # High P(SL) when the safety members are *bad*, so their weights are negative.
    sl = {
        _M.RISK.value: -1.2,
        _M.SECURITY.value: -1.0,
        _M.DEVELOPER.value: -0.8,
        _M.HOLDER_DISTRIBUTION.value: -0.7,
        _M.LIQUIDITY.value: -0.7,
        _M.VOLATILITY.value: -0.6,
        _M.WALLET.value: -0.6,
        _M.BEHAVIOR.value: -0.5,
        _M.MOMENTUM.value: -0.4,
    }
    return {
        ROI_POSITIVE: ModelWeights(bias=-0.15, coefficients=roi),
        HIT_TP: ModelWeights(bias=-0.35, coefficients=tp),
        HIT_SL: ModelWeights(bias=0.15, coefficients=sl),
    }


class MetaModel:
    """Fuses committee opinions into three calibrated probabilities."""

    def __init__(
        self, heads: dict[str, ModelWeights] | None = None, *, version: str = "default"
    ) -> None:
        self._heads = heads or _default_head_weights()
        self._version = version

    @property
    def version(self) -> str:
        return self._version

    @property
    def heads(self) -> dict[str, ModelWeights]:
        return self._heads

    def fuse(self, token: TokenRef, opinions: Sequence[Opinion]) -> MetaPrediction:
        by_member = {o.member.value: o for o in opinions}
        roi = self._head(ROI_POSITIVE, by_member)
        tp = self._head(HIT_TP, by_member)
        sl = self._head(HIT_SL, by_member)
        confidence = self._fusion_confidence(opinions)
        return MetaPrediction(
            token=token,
            prob_roi_positive=round(roi, 4),
            prob_hit_tp=round(tp, 4),
            prob_hit_sl=round(sl, 4),
            confidence=round(confidence, 4),
            member_probabilities={m: round(o.probability, 4) for m, o in by_member.items()},
            model_version=self._version,
        )

    # -- internals ------------------------------------------------------------

    def _head(self, name: str, by_member: dict[str, Opinion]) -> float:
        weights = self._heads[name]
        z = weights.bias
        for member, weight in weights.coefficients.items():
            opinion = by_member.get(member)
            if opinion is None or opinion.abstained:
                continue
            centred = (opinion.probability - 0.5) * 2.0  # [-1, 1]
            z += weight * centred * opinion.confidence
        return sigmoid(z)

    @staticmethod
    def _fusion_confidence(opinions: Sequence[Opinion]) -> float:
        active = [o for o in opinions if not o.abstained]
        if not active:
            return 0.1
        avg_conf = sum(o.confidence for o in active) / len(active)
        participation = len(active) / max(1, len(opinions))
        return clamp(0.6 * avg_conf + 0.4 * participation)

"""Explainability Engine — turn a committee verdict into a legible account.

The spec forbids answering with a bare percentage. Every prediction must come
with the reasons *for* it (drivers), the reasons it is not higher (risks), and
the reasons to distrust the number itself (caveats — low coverage, thin data,
unstable regime). This builder assembles that :class:`CommitteeExplanation` from
the specialists' own reasons and the confidence decomposition, ranking drivers by
how strongly they moved their specialist and how confident that specialist was.
"""

from __future__ import annotations

from collections.abc import Sequence

from hades.contexts.learning.domain.models import (
    CommitteeExplanation,
    ConfidenceFactors,
    Direction,
    MetaPrediction,
    Opinion,
    RegimeAssessment,
)

_LOW_COVERAGE = 0.5
_LOW_DATA = 0.4
_LOW_AGREEMENT = 0.45


class ExplanationBuilder:
    """Composes a human-readable explanation of the committee's verdict."""

    def build(
        self,
        *,
        meta: MetaPrediction,
        opinions: Sequence[Opinion],
        confidence: ConfidenceFactors,
        regime: RegimeAssessment,
        max_items: int = 5,
    ) -> CommitteeExplanation:
        drivers = self._collect(opinions, Direction.UP, max_items)
        risks = self._collect(opinions, Direction.DOWN, max_items)
        caveats = self._caveats(confidence, regime)
        return CommitteeExplanation(
            headline=self._headline(meta, confidence),
            drivers=drivers,
            risks=risks,
            caveats=caveats,
        )

    # -- internals ------------------------------------------------------------

    @staticmethod
    def _headline(meta: MetaPrediction, confidence: ConfidenceFactors) -> str:
        roi = round(meta.prob_roi_positive * 100.0)
        tp = round(meta.prob_hit_tp * 100.0)
        sl = round(meta.prob_hit_sl * 100.0)
        conf = round(confidence.final * 100.0)
        return (
            f"P(ROI+) {roi}% · P(TP) {tp}% · P(SL) {sl}% "
            f"at {conf}% confidence — evidence only, not a decision."
        )

    @staticmethod
    def _collect(opinions: Sequence[Opinion], direction: Direction, limit: int) -> tuple[str, ...]:
        scored: list[tuple[float, str]] = []
        for opinion in opinions:
            if opinion.abstained:
                continue
            for reason in opinion.reasons:
                if reason.direction is not direction:
                    continue
                weight = abs(reason.contribution) * (0.4 + 0.6 * opinion.confidence)
                label = opinion.member.value.replace("_", " ")
                scored.append((weight, f"{label}: {reason.text}"))
        scored.sort(key=lambda kv: kv[0], reverse=True)
        seen: set[str] = set()
        out: list[str] = []
        for _, text in scored:
            if text in seen:
                continue
            seen.add(text)
            out.append(text)
            if len(out) >= limit:
                break
        return tuple(out)

    @staticmethod
    def _caveats(confidence: ConfidenceFactors, regime: RegimeAssessment) -> tuple[str, ...]:
        caveats: list[str] = []
        if confidence.coverage < _LOW_COVERAGE:
            caveats.append(
                f"partial data — only {round(confidence.coverage * 100)}% of features present"
            )
        if confidence.dataset_quality < _LOW_DATA or confidence.sample_support < _LOW_DATA:
            caveats.append("thin training history for tokens like this")
        if confidence.agreement < _LOW_AGREEMENT:
            caveats.append("specialists disagree — low corroboration")
        if confidence.volatility_penalty >= 0.5:
            caveats.append("elevated volatility reduces reliability")
        if regime.confidence < 0.35:
            caveats.append("market regime is ambiguous")
        return tuple(caveats)

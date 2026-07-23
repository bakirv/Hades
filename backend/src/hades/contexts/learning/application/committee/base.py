"""The base of every committee specialist — a transparent logistic model.

A specialist is a single-purpose analyst. It looks only at its own slice of the
feature vector and answers one narrow question with a *probability*, a
*confidence* and the *reasons* behind both — never a decision. The model is a
linear-logistic scorer:

    z = bias + Σ weightᵢ · featureᵢ
    probability = sigmoid(z)

Because every term ``weightᵢ · featureᵢ`` is a legible contribution, an opinion
decomposes exactly into "this feature pushed me up by X, that one down by Y".
That is the whole point: no black boxes. The weights are *data* — supplied by the
registry (trained) or by a documented default — so the same class serves a
freshly-seeded model and a retrained one.

Confidence is not the probability. It blends how much of the model's feature set
was actually present (coverage) with how decisive the signal was (distance of
the logit from zero). A specialist that cannot see its inputs *abstains* — it
returns a neutral 0.5 with near-zero confidence rather than pretending.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from hades.contexts.learning.application.mathx import clamp, sigmoid
from hades.contexts.learning.domain.models import (
    CommitteeMember,
    Direction,
    ModelWeights,
    NormalizedVector,
    Opinion,
    Reason,
)


@dataclass(frozen=True)
class ReasonTemplate:
    """Human phrasing for a feature when it drives an opinion up or down."""

    feature: str
    high: str  # phrasing when the (normalised) feature is high
    low: str  # phrasing when it is low


@dataclass(frozen=True)
class SpecialistSpec:
    """The declarative definition of one specialist: what it looks at and how.

    ``default_weights`` are documented priors so the committee is meaningful from
    day one, before any training. ``min_coverage`` is the fraction of the
    specialist's own features that must be present for it to have a view.
    """

    member: CommitteeMember
    question: str
    default_bias: float
    default_weights: dict[str, float] = field(default_factory=dict)
    reason_templates: tuple[ReasonTemplate, ...] = ()
    min_coverage: float = 0.34
    max_reasons: int = 4


class SpecialistModel:
    """A committee member: a transparent logistic scorer over its own features."""

    def __init__(self, spec: SpecialistSpec, weights: ModelWeights, version: str = "0") -> None:
        self._spec = spec
        self._weights = weights
        self._version = version
        self._templates = {t.feature: t for t in spec.reason_templates}

    @property
    def member(self) -> CommitteeMember:
        return self._spec.member

    @property
    def version(self) -> str:
        return self._version

    @property
    def feature_names(self) -> tuple[str, ...]:
        return tuple(self._weights.coefficients.keys())

    @classmethod
    def from_defaults(cls, spec: SpecialistSpec, version: str = "default") -> SpecialistModel:
        return cls(
            spec,
            ModelWeights(bias=spec.default_bias, coefficients=dict(spec.default_weights)),
            version=version,
        )

    def evaluate(self, vector: NormalizedVector) -> Opinion:
        coefficients = self._weights.coefficients
        present = [f for f in coefficients if f in vector.values]
        coverage = len(present) / len(coefficients) if coefficients else 0.0

        if coverage < self._spec.min_coverage:
            return self._abstain(coverage)

        # ``z`` uses the raw terms (the actual logit); the *reasons* use each
        # feature's contribution relative to its neutral point, so a low value of
        # a negatively-weighted feature (e.g. low concentration) reads as a driver
        # UP rather than a spurious risk. Feature-store values sit in [0, 1] with a
        # 0.5 neutral (a handful of z-score features are centred on 0).
        contributions: list[tuple[str, float]] = []
        z = self._weights.bias
        for feature in present:
            value = vector.values[feature]
            z += coefficients[feature] * value
            neutral = 0.5 if 0.0 <= value <= 1.0 else 0.0
            contributions.append((feature, coefficients[feature] * (value - neutral)))

        probability = sigmoid(z)
        confidence = self._confidence(coverage, z)
        reasons = self._reasons(contributions, vector)
        positives, negatives = self._legends(reasons)
        return Opinion(
            member=self._spec.member,
            probability=probability,
            confidence=confidence,
            summary=self._summary(probability, coverage),
            reasons=reasons,
            positives=positives,
            negatives=negatives,
            features_used=len(present),
            model_version=self._version,
            abstained=False,
        )

    # -- internals ------------------------------------------------------------

    def _abstain(self, coverage: float) -> Opinion:
        return Opinion(
            member=self._spec.member,
            probability=0.5,
            confidence=round(0.15 * coverage, 4),
            summary="Insufficient data to form a view.",
            features_used=0,
            model_version=self._version,
            abstained=True,
        )

    @staticmethod
    def _confidence(coverage: float, z: float) -> float:
        # Decisiveness: how far the logit is from the indifferent point (0).
        decisiveness = clamp(abs(z) / 3.0)
        return round(
            clamp(0.35 * coverage + 0.45 * decisiveness + 0.2 * coverage * decisiveness), 4
        )

    def _reasons(
        self, contributions: Sequence[tuple[str, float]], vector: NormalizedVector
    ) -> tuple[Reason, ...]:
        ordered = sorted(contributions, key=lambda kv: abs(kv[1]), reverse=True)
        reasons: list[Reason] = []
        for feature, term in ordered[: self._spec.max_reasons]:
            if abs(term) < 1e-4:
                continue
            direction = Direction.UP if term >= 0 else Direction.DOWN
            reasons.append(
                Reason(
                    feature=feature,
                    text=self._phrase(feature, vector),
                    contribution=round(term, 4),
                    direction=direction,
                )
            )
        return tuple(reasons)

    def _phrase(self, feature: str, vector: NormalizedVector) -> str:
        template = self._templates.get(feature)
        normalised = vector.values.get(feature, 0.0)
        if template is None:
            label = feature.split(".")[-1].replace("_", " ")
            return f"{label} {'elevated' if normalised >= 0.5 else 'low'}"
        return template.high if normalised >= 0.5 else template.low

    @staticmethod
    def _legends(reasons: Sequence[Reason]) -> tuple[tuple[str, ...], tuple[str, ...]]:
        positives = tuple(r.text for r in reasons if r.direction is Direction.UP)
        negatives = tuple(r.text for r in reasons if r.direction is Direction.DOWN)
        return positives, negatives

    def _summary(self, probability: float, coverage: float) -> str:
        pct = round(probability * 100.0)
        cov = round(coverage * 100.0)
        return f"{self._spec.question} → {pct}% (on {cov}% of inputs)"

"""Unit tests for the AI Committee building blocks (pure, no I/O)."""

from __future__ import annotations

from datetime import UTC, datetime

from hades.contexts.common.domain.value_objects import TokenMint, TokenRef
from hades.contexts.features.domain.models import FeatureSet
from hades.contexts.learning.application import mathx
from hades.contexts.learning.application.committee.factory import default_committee
from hades.contexts.learning.application.committee.specialists import default_specialists
from hades.contexts.learning.application.confidence import ConfidenceEngine
from hades.contexts.learning.application.explainability import ExplanationBuilder
from hades.contexts.learning.application.feature_catalog import FeatureCatalog, FeatureNormalizer
from hades.contexts.learning.application.regime import MarketRegimeClassifier
from hades.contexts.learning.domain.models import CommitteeMember, MarketRegime, NormalizedVector

_TOKEN = TokenRef(mint=TokenMint(address="M" * 44))


def _vector(values: dict[str, float]) -> NormalizedVector:
    return NormalizedVector(token=_TOKEN, at=datetime.now(UTC), values=values, coverage=1.0)


# --- mathx -------------------------------------------------------------------


def test_sigmoid_bounds_and_monotonic() -> None:
    assert 0.0 < mathx.sigmoid(-50.0) < mathx.sigmoid(0.0) < mathx.sigmoid(50.0) <= 1.0
    assert abs(mathx.sigmoid(0.0) - 0.5) < 1e-9
    assert mathx.sigmoid(-2.0) < mathx.sigmoid(-1.0) < mathx.sigmoid(1.0) < mathx.sigmoid(2.0)


def test_roc_auc_perfect_and_random() -> None:
    perfect = [(0.9, 1), (0.8, 1), (0.2, 0), (0.1, 0)]
    assert mathx.roc_auc(perfect) == 1.0
    # A single class present is undefined -> reported as 0.5.
    assert mathx.roc_auc([(0.5, 1), (0.6, 1)]) == 0.5


def test_brier_and_calibration() -> None:
    assert mathx.brier_score([(1.0, 1), (0.0, 0)]) == 0.0
    assert mathx.calibration_error([(1.0, 1), (0.0, 0)]) == 0.0


# --- feature normalizer ------------------------------------------------------


def test_normalizer_bounds_and_coverage() -> None:
    catalog = FeatureCatalog()
    normalizer = FeatureNormalizer(catalog)
    fs = FeatureSet(
        token=_TOKEN,
        computed_at=datetime.now(UTC),
        values={"basic.liquidity": 250_000.0, "basic.spread_bps": 30.0, "holders.gini": 0.4},
    )
    vector = normalizer.normalize(fs)
    for value in vector.values.values():
        assert -3.0 <= value <= 3.0
    # coverage is the fraction of the catalog present.
    assert 0.0 < vector.coverage < 1.0
    assert vector.values["basic.liquidity"] > 0.5  # deep liquidity -> high


def test_normalizer_bool_and_missing() -> None:
    normalizer = FeatureNormalizer(FeatureCatalog())
    fs = FeatureSet(token=_TOKEN, computed_at=datetime.now(UTC), values={"pool.lp_locked": 1.0})
    vector = normalizer.normalize(fs)
    assert vector.values["pool.lp_locked"] == 1.0
    assert "tech.rsi_14" not in vector.values  # absent stays absent (neutral downstream)


# --- specialists -------------------------------------------------------------


def test_all_twelve_specialists_present() -> None:
    members = {s.member for s in default_specialists()}
    assert members == set(CommitteeMember)


def test_specialist_abstains_without_features() -> None:
    liquidity = next(s for s in default_specialists() if s.member is CommitteeMember.LIQUIDITY)
    opinion = liquidity.evaluate(_vector({}))
    assert opinion.abstained
    assert opinion.probability == 0.5
    assert opinion.confidence < 0.2


def test_specialist_opinion_is_explainable() -> None:
    liquidity = next(s for s in default_specialists() if s.member is CommitteeMember.LIQUIDITY)
    good = liquidity.evaluate(
        _vector(
            {
                "basic.liquidity": 0.9,
                "pool.depth_usd": 0.8,
                "basic.liquidity_to_mcap": 0.7,
                "basic.spread_bps": 0.1,
                "basic.slippage_bps": 0.1,
            }
        )
    )
    assert not good.abstained
    assert good.probability > 0.6
    assert good.reasons  # never just a number
    assert good.summary


def test_specialist_direction_reflects_health() -> None:
    liquidity = next(s for s in default_specialists() if s.member is CommitteeMember.LIQUIDITY)
    bad = liquidity.evaluate(
        _vector(
            {
                "basic.liquidity": 0.05,
                "pool.depth_usd": 0.05,
                "basic.spread_bps": 0.9,
                "basic.slippage_bps": 0.9,
            }
        )
    )
    assert bad.probability < 0.5
    assert bad.negatives  # a thin/wide-spread pool yields negative reasons


# --- regime ------------------------------------------------------------------


def test_regime_bull_and_lowliquidity() -> None:
    classifier = MarketRegimeClassifier()
    bull = classifier.classify(
        _vector(
            {
                "regime.macro_trend": 0.9,
                "regime.micro_trend": 0.85,
                "tech.trend_alignment": 0.9,
                "tech.price_slope": 0.6,
                "basic.buyer_seller_ratio": 0.8,
                "tech.volatility": 0.1,
                "basic.liquidity": 0.8,
                "basic.trades_5m": 0.7,
            }
        )
    )
    assert bull.regime is MarketRegime.BULL
    assert bull.confidence > 0.0

    thin = classifier.classify(_vector({"basic.liquidity": 0.02, "basic.trades_5m": 0.02}))
    assert thin.regime is MarketRegime.LOW_LIQUIDITY


def test_regime_unknown_when_no_features() -> None:
    assert (
        MarketRegimeClassifier()
        .classify(NormalizedVector(token=_TOKEN, at=datetime.now(UTC), coverage=0.0))
        .regime
        is MarketRegime.UNKNOWN
    )


# --- meta + confidence + explainability --------------------------------------


def test_meta_produces_three_probabilities() -> None:
    committee = default_committee()
    vector = _vector(
        {
            "basic.liquidity": 0.8,
            "tech.price_slope": 0.7,
            "security.score": 0.85,
            "security.approved": 1.0,
            "intel.smart_money_ratio": 0.7,
            "holders.gini": 0.3,
            "tech.volatility": 0.2,
        }
    )
    opinions = [s.evaluate(vector) for s in committee.specialists]
    meta = committee.meta.fuse(_TOKEN, opinions)
    for p in (meta.prob_roi_positive, meta.prob_hit_tp, meta.prob_hit_sl, meta.confidence):
        assert 0.0 <= p <= 1.0
    assert meta.member_probabilities  # auditable per-member echo


def test_confidence_is_multifactor() -> None:
    committee = default_committee()
    vector = _vector({"basic.liquidity": 0.8, "security.score": 0.8, "security.approved": 1.0})
    opinions = [s.evaluate(vector) for s in committee.specialists]
    regime = MarketRegimeClassifier().classify(vector)
    factors = ConfidenceEngine().compute(
        opinions=opinions,
        regime=regime,
        coverage=vector.coverage,
        volatility=0.8,
        dataset_quality=0.3,
        sample_support=0.2,
    )
    # High volatility + poor data must pull the final below the raw coverage.
    assert factors.final < factors.coverage
    assert factors.volatility_penalty == 0.8


def test_explanation_never_bare_number() -> None:
    committee = default_committee()
    vector = _vector({"basic.liquidity": 0.85, "security.score": 0.85, "security.approved": 1.0})
    opinions = [s.evaluate(vector) for s in committee.specialists]
    meta = committee.meta.fuse(_TOKEN, opinions)
    regime = MarketRegimeClassifier().classify(vector)
    factors = ConfidenceEngine().compute(
        opinions=opinions,
        regime=regime,
        coverage=vector.coverage,
        volatility=0.2,
        dataset_quality=0.6,
        sample_support=0.5,
    )
    explanation = ExplanationBuilder().build(
        meta=meta, opinions=opinions, confidence=factors, regime=regime
    )
    assert explanation.headline
    assert explanation.drivers or explanation.risks

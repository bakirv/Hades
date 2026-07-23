"""Unit tests for the pure Wallet Intelligence engines.

Reputation evolution, behaviour classification, smart/dumb money, influence,
funding classification, clustering and scoring — all deterministic, no I/O.
"""

from __future__ import annotations

from datetime import UTC, datetime

from hades.contexts.common.domain.value_objects import TokenMint, TokenRef
from hades.contexts.intelligence.application.behavior import BehaviorEngine, BehaviorEvidence
from hades.contexts.intelligence.application.clustering import ClusterBuilder
from hades.contexts.intelligence.application.funding import FundingAnalyzer
from hades.contexts.intelligence.application.influence import InfluenceEngine
from hades.contexts.intelligence.application.reputation import (
    ReputationEngine,
    ReputationEvidence,
)
from hades.contexts.intelligence.application.scoring import WalletScorer
from hades.contexts.intelligence.application.smart_money import MoneyEvidence, SmartMoneyEngine
from hades.contexts.intelligence.domain.models import (
    BehaviorType,
    FundingSourceKind,
    MoneyClass,
    ReputationBand,
    ReputationScores,
    WalletObservation,
    WalletObservationBatch,
    WalletRole,
    WalletScoreBreakdown,
)

_A = "A" * 44
_B = "B" * 44
_C = "C" * 44
_F = "F" * 44


def _token() -> TokenRef:
    return TokenRef(mint=TokenMint(address="M" * 44))


# -- reputation ---------------------------------------------------------------


def test_reputation_starts_neutral_and_scammer_is_floored() -> None:
    engine = ReputationEngine()
    scammer = engine.evolve(
        ReputationScores.initial(),
        ReputationEvidence(
            tokens_traded=1,
            launches=0,
            rugs_participated=0,
            successes=0,
            age_hours=1.0,
            is_known_scammer=True,
        ),
    )
    assert scammer.trust < 30.0
    assert scammer.risk > 70.0


def test_reputation_rewards_clean_success_and_experience_ratchets() -> None:
    engine = ReputationEngine(alpha=0.5)
    prior = ReputationScores.initial()
    good = engine.evolve(
        prior,
        ReputationEvidence(
            tokens_traded=20,
            launches=3,
            rugs_participated=0,
            successes=8,
            age_hours=1000.0,
            is_known_scammer=False,
        ),
    )
    assert good.trust > prior.trust
    assert good.experience > prior.experience
    # Experience never regresses even if the next evidence is thinner.
    thin = engine.evolve(
        good,
        ReputationEvidence(
            tokens_traded=1,
            launches=0,
            rugs_participated=0,
            successes=0,
            age_hours=1.0,
            is_known_scammer=False,
        ),
    )
    assert thin.experience >= good.experience


def test_reputation_punishes_rug_participation() -> None:
    engine = ReputationEngine(alpha=0.6)
    rugger = engine.evolve(
        ReputationScores.initial(),
        ReputationEvidence(
            tokens_traded=10,
            launches=0,
            rugs_participated=8,
            successes=1,
            age_hours=500.0,
            is_known_scammer=False,
        ),
    )
    assert rugger.risk > 60.0
    assert rugger.trust < 40.0


# -- behaviour ----------------------------------------------------------------


def test_behavior_classifies_whale_and_unknown() -> None:
    engine = BehaviorEngine()
    unknown = engine.classify(
        BehaviorEvidence(
            tokens_traded=0,
            launches=0,
            observations=0,
            age_hours=0.0,
            avg_pct_supply=0.0,
            max_pct_supply=0.0,
        )
    )
    assert unknown.behavior is BehaviorType.UNKNOWN
    whale = engine.classify(
        BehaviorEvidence(
            tokens_traded=3,
            launches=0,
            observations=4,
            age_hours=100.0,
            avg_pct_supply=8.0,
            max_pct_supply=12.0,
        )
    )
    assert whale.behavior is BehaviorType.WHALE
    assert whale.confidence > 0.0


# -- smart / dumb money -------------------------------------------------------


def test_smart_money_needs_resolved_history() -> None:
    engine = SmartMoneyEngine(min_resolved=3)
    rep = ReputationScores(trust=80, risk=20, consistency=80, experience=70, profitability=85)
    neutral = engine.evaluate(
        rep,
        MoneyEvidence(rugs_participated=0, successes=1, tokens_traded=5, is_known_scammer=False),
    )
    assert neutral.money_class is MoneyClass.NEUTRAL
    smart = engine.evaluate(
        rep,
        MoneyEvidence(rugs_participated=0, successes=6, tokens_traded=8, is_known_scammer=False),
    )
    assert smart.money_class is MoneyClass.SMART
    assert smart.score.value > 68.0


def test_dumb_money_from_rugs() -> None:
    engine = SmartMoneyEngine()
    rep = ReputationScores(trust=30, risk=80, consistency=30, experience=40, profitability=20)
    dumb = engine.evaluate(
        rep,
        MoneyEvidence(rugs_participated=6, successes=1, tokens_traded=8, is_known_scammer=False),
    )
    assert dumb.money_class is MoneyClass.DUMB


# -- influence ----------------------------------------------------------------


def test_influence_scales_with_evidence() -> None:
    engine = InfluenceEngine()
    rep = ReputationScores(trust=85, risk=15, consistency=85, experience=80, profitability=85)
    thin = engine.compute(rep, smart_money_score=85.0, observations=1)
    rich = engine.compute(rep, smart_money_score=85.0, observations=10)
    assert rich > thin
    assert rich <= 100.0


# -- funding ------------------------------------------------------------------


def test_funding_flags_mixer_and_scammer() -> None:
    batch = WalletObservationBatch(
        token=_token(),
        now=datetime.now(UTC),
        observations=(),
        known_scammers=frozenset({_A}),
        known_mixers=frozenset({_B}),
        known_exchanges=frozenset({_C}),
    )
    links = FundingAnalyzer().classify((_A, _B, _C, _F), batch)
    kinds = {link.source: link.kind for link in links}
    assert kinds[_A] is FundingSourceKind.SUSPICIOUS
    assert kinds[_B] is FundingSourceKind.MIXER
    assert kinds[_C] is FundingSourceKind.EXCHANGE
    assert kinds[_F] is FundingSourceKind.WALLET


# -- clustering ---------------------------------------------------------------


def test_clustering_groups_common_funder() -> None:
    now = datetime.now(UTC)
    obs = tuple(
        WalletObservation(address=a, role=WalletRole.HOLDER, pct_supply=5.0, funders=(_F,), at=now)
        for a in (_A, _B, _C)
    )
    batch = WalletObservationBatch(token=_token(), now=now, observations=obs)
    clusters = ClusterBuilder(min_members=3).build(batch)
    assert len(clusters) == 1
    assert clusters[0].funder == _F
    assert clusters[0].size == 3
    assert clusters[0].pct_supply == 15.0

    # Below the member threshold → no cluster.
    small = WalletObservationBatch(token=_token(), now=now, observations=obs[:2])
    assert ClusterBuilder(min_members=3).build(small) == ()


def test_cluster_id_is_deterministic() -> None:
    now = datetime.now(UTC)
    obs = tuple(
        WalletObservation(address=a, role=WalletRole.HOLDER, pct_supply=1.0, funders=(_F,), at=now)
        for a in (_A, _B, _C)
    )
    batch = WalletObservationBatch(token=_token(), now=now, observations=obs)
    a = ClusterBuilder(min_members=3).build(batch)
    b = ClusterBuilder(min_members=3).build(batch)
    assert a[0].cluster_id == b[0].cluster_id


# -- scoring ------------------------------------------------------------------


def test_scorer_floors_scammer_and_bands_trusted() -> None:
    scorer = WalletScorer()
    strong = WalletScoreBreakdown(
        trust=85,
        risk=15,
        smart_money=80,
        consistency=85,
        influence=70,
        experience=80,
        behavior=60,
        profitability=85,
    )
    trusted = scorer.score(strong, money_class=MoneyClass.SMART, is_scammer=False)
    assert trusted.band in (ReputationBand.SMART_MONEY, ReputationBand.TRUSTED)
    assert trusted.score.value > 62.0

    scammer = scorer.score(strong, money_class=MoneyClass.SMART, is_scammer=True)
    assert scammer.band is ReputationBand.SCAMMER
    assert scammer.score.value < 10.0

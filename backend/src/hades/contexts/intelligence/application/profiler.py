"""Wallet Profiler — fold one observation into an evolving wallet profile.

This is the registry + profiling core. Given the wallet's prior profile (or
nothing, for a first sighting) and a fresh :class:`WalletObservation`, it produces
the next immutable profile version: monotonic activity counts grow, reputation
evolves, behaviour is re-classified, smart-money and influence are re-measured,
and the final Wallet Score and its explanation are rebuilt. The previous version
is never lost — the engine hands it to the append-only knowledge base.

Pure and deterministic: all evidence arrives in its arguments; it does no I/O.
"""

from __future__ import annotations

from datetime import datetime

from hades.contexts.common.domain.value_objects import WalletAddress
from hades.contexts.intelligence.application.behavior import BehaviorEngine, BehaviorEvidence
from hades.contexts.intelligence.application.explainability import build_wallet_explanation
from hades.contexts.intelligence.application.influence import InfluenceEngine
from hades.contexts.intelligence.application.reputation import (
    ReputationEngine,
    ReputationEvidence,
)
from hades.contexts.intelligence.application.scoring import WalletScorer
from hades.contexts.intelligence.application.smart_money import MoneyEvidence, SmartMoneyEngine
from hades.contexts.intelligence.domain.models import (
    FundingLink,
    ReputationScores,
    WalletObservation,
    WalletProfile,
    WalletRole,
    WalletScoreBreakdown,
)

_INACTIVE_DAYS = 30


class WalletProfiler:
    """Builds the next :class:`WalletProfile` version from a new observation."""

    def __init__(
        self,
        *,
        reputation: ReputationEngine,
        behavior: BehaviorEngine,
        smart_money: SmartMoneyEngine,
        influence: InfluenceEngine,
        scorer: WalletScorer,
    ) -> None:
        self._reputation = reputation
        self._behavior = behavior
        self._smart_money = smart_money
        self._influence = influence
        self._scorer = scorer

    def build(
        self,
        prior: WalletProfile | None,
        observation: WalletObservation,
        *,
        funding: tuple[FundingLink, ...],
        cluster_id: str | None,
        now: datetime,
    ) -> WalletProfile:
        address = WalletAddress(address=observation.address)
        first_seen = prior.first_seen_at if prior else observation.at
        prior_avg = prior.avg_pct_supply if prior else 0.0

        observations = (prior.observations if prior else 0) + 1
        tokens_traded = (prior.tokens_traded if prior else 0) + 1
        launches = (prior.launches if prior else 0) + (
            1 if observation.role is WalletRole.DEPLOYER else 0
        )
        rugs = prior.rugs_participated if prior else 0
        successes = prior.successes if prior else 0
        dexes = _extend(prior.dexes if prior else (), observation.dex)
        roles = _extend(prior.roles if prior else (), observation.role.value)
        avg_pct = _running_mean(prior_avg, observations - 1, observation.pct_supply)
        merged_funding = _merge_funding(prior.funding if prior else (), funding)
        age_hours = max(0.0, (now - first_seen).total_seconds() / 3600.0)

        reputation = self._reputation.evolve(
            prior.reputation if prior else ReputationScores.initial(),
            ReputationEvidence(
                tokens_traded=tokens_traded,
                launches=launches,
                rugs_participated=rugs,
                successes=successes,
                age_hours=age_hours,
                is_known_scammer=observation.is_known_scammer,
                consistency_signal=_consistency_signal(observations, age_hours),
            ),
        )
        behavior = self._behavior.classify(
            BehaviorEvidence(
                tokens_traded=tokens_traded,
                launches=launches,
                observations=observations,
                age_hours=age_hours,
                avg_pct_supply=avg_pct,
                max_pct_supply=max(prior_avg, observation.pct_supply),
            )
        )
        money = self._smart_money.evaluate(
            reputation,
            MoneyEvidence(
                rugs_participated=rugs,
                successes=successes,
                tokens_traded=tokens_traded,
                is_known_scammer=observation.is_known_scammer,
            ),
        )
        influence = self._influence.compute(
            reputation,
            smart_money_score=money.score.value,
            observations=observations,
        )
        breakdown = WalletScoreBreakdown(
            trust=reputation.trust,
            risk=reputation.risk,
            smart_money=money.score.value,
            consistency=reputation.consistency,
            influence=influence,
            experience=reputation.experience,
            behavior=50.0 + 20.0 * behavior.confidence,
            profitability=reputation.profitability,
        )
        result = self._scorer.score(
            breakdown, money_class=money.money_class, is_scammer=observation.is_known_scammer
        )
        explanation = build_wallet_explanation(
            address=observation.address,
            final_score=result.score.value,
            band=result.band,
            reputation=reputation,
            behavior=behavior,
            tokens_traded=tokens_traded,
            launches=launches,
            rugs_participated=rugs,
            successes=successes,
            funding_kinds=tuple(link.kind for link in merged_funding),
            smart_money_score=money.score.value,
            inactive=_is_inactive(prior, now),
            cluster_id=cluster_id,
        )
        return WalletProfile(
            address=address,
            first_seen_at=first_seen,
            last_active_at=now,
            observations=observations,
            tokens_traded=tokens_traded,
            launches=launches,
            rugs_participated=rugs,
            successes=successes,
            dexes=dexes,
            roles=roles,
            avg_pct_supply=round(avg_pct, 4),
            reputation=reputation,
            behavior=behavior,
            money_class=money.money_class,
            smart_money_score=money.score,
            influence=round(influence, 2),
            funding=merged_funding,
            cluster_id=cluster_id
            if cluster_id is not None
            else (prior.cluster_id if prior else None),
            score=result.score,
            band=result.band,
            explanation=explanation,
            version=(prior.version + 1) if prior else 1,
        )


def _extend(existing: tuple[str, ...], value: str | None) -> tuple[str, ...]:
    if value is None or value in existing:
        return existing
    return (*existing, value)


def _running_mean(prior_mean: float, prior_count: int, new_value: float) -> float:
    if prior_count <= 0:
        return new_value
    return (prior_mean * prior_count + new_value) / (prior_count + 1)


def _merge_funding(
    existing: tuple[FundingLink, ...], fresh: tuple[FundingLink, ...]
) -> tuple[FundingLink, ...]:
    seen = {link.source for link in existing}
    merged = list(existing)
    for link in fresh:
        if link.source not in seen:
            merged.append(link)
            seen.add(link.source)
    return tuple(merged)


def _consistency_signal(observations: int, age_hours: float) -> float:
    """A cheap regularity proxy until per-trade timing is available.

    Wallets active steadily over time read as more consistent than a burst.
    """
    if age_hours <= 0:
        return 0.5
    per_day = observations / max(age_hours / 24.0, 1e-3)
    # Very bursty (many ops, tiny age) or totally idle both read as less regular.
    return max(0.0, min(1.0, 1.0 - abs(per_day - 1.0) / 10.0))


def _is_inactive(prior: WalletProfile | None, now: datetime) -> bool:
    if prior is None:
        return False
    return (now - prior.last_active_at).days >= _INACTIVE_DAYS

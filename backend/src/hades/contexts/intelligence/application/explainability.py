"""Explainability — every wallet score must be legible.

A Wallet Score is never returned as a bare number. For each wallet this builds the
positives that lifted it, the negatives that dragged it down, and a one-line
summary — the exact "+ participated in 37 successful launches / - no activity in
30 days" account the spec asks for. This is what the dashboard shows and what a
human uses to trust, or challenge, the machine.
"""

from __future__ import annotations

from hades.contexts.intelligence.domain.models import (
    BehaviorProfile,
    FundingSourceKind,
    ReputationBand,
    ReputationScores,
    WalletExplanation,
)


def build_wallet_explanation(
    *,
    address: str,
    final_score: float,
    band: ReputationBand,
    reputation: ReputationScores,
    behavior: BehaviorProfile,
    tokens_traded: int,
    launches: int,
    rugs_participated: int,
    successes: int,
    funding_kinds: tuple[FundingSourceKind, ...],
    smart_money_score: float,
    inactive: bool,
    cluster_id: str | None,
) -> WalletExplanation:
    """Assemble the ordered positive/negative reasons and a summary line."""
    positives: list[str] = []
    negatives: list[str] = []

    if successes:
        positives.append(f"Participated in {successes} successful project(s).")
    if rugs_participated == 0 and (rugs_participated + successes) > 0:
        positives.append("Never observed participating in a rug.")
    if smart_money_score >= 70.0:
        positives.append(f"High smart-money score ({smart_money_score:.0f}/100).")
    if reputation.experience >= 60.0:
        positives.append(f"Experienced wallet (experience {reputation.experience:.0f}/100).")
    if reputation.consistency >= 70.0:
        positives.append("Consistent, regular trading pattern.")
    if behavior.confidence >= 0.5 and behavior.detail:
        positives.append(behavior.detail)

    if band is ReputationBand.SCAMMER:
        negatives.append("Wallet is blacklisted as a known scammer.")
    if rugs_participated:
        negatives.append(f"Participated in {rugs_participated} rug(s).")
    if reputation.risk >= 65.0:
        negatives.append(f"Elevated risk score ({reputation.risk:.0f}/100).")
    if tokens_traded == 0:
        negatives.append("Brand-new wallet with no track record yet.")
    if FundingSourceKind.MIXER in funding_kinds:
        negatives.append("Funded through a mixer.")
    if FundingSourceKind.SUSPICIOUS in funding_kinds:
        negatives.append("Funded by a blacklisted wallet.")
    if cluster_id is not None:
        negatives.append(f"Belongs to coordinated wallet cluster {cluster_id}.")
    if inactive:
        negatives.append("No activity observed in the last 30 days.")

    summary = (
        f"Wallet {_short(address)} scored {final_score:.0f}/100 ({band.value}) — "
        f"{len(positives)} positive, {len(negatives)} negative signal(s)."
    )
    return WalletExplanation(
        summary=summary, positives=tuple(positives), negatives=tuple(negatives)
    )


def _short(address: str) -> str:
    return f"{address[:4]}…{address[-4:]}" if len(address) > 10 else address

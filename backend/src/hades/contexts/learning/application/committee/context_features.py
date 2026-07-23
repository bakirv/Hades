"""Derive the ``security.*`` and ``intel.*`` context features for the committee.

The Security verdict and Wallet-Intelligence snapshot do not come from the
Feature Engine — they arrive on the :class:`DecisionContext`. This module turns
them into the same kind of pre-normalised [0, 1] feature values the specialists
consume, so the Security / Wallet / Developer / Behaviour / Risk models can run
through the exact same transparent-logistic mechanism as everyone else.

Everything is a documented, bounded transform. Missing upstream data simply
yields fewer keys (the dependent specialist then sees lower coverage and lowers
its own confidence — it never errors).
"""

from __future__ import annotations

from hades.contexts.learning.application.mathx import clamp
from hades.contexts.learning.domain.models import DecisionContext

#: Supply concentration (largest cluster %) at which "cluster pressure" saturates.
_CLUSTER_PCT_SATURATION = 40.0
#: Cluster count at which "cluster count" saturates.
_CLUSTER_COUNT_SATURATION = 5.0
#: Smart-money supply share at which the feature saturates.
_SMART_SUPPLY_SATURATION = 30.0


def context_feature_values(ctx: DecisionContext) -> dict[str, float]:
    """Compute the injected context features from a decision context."""
    values: dict[str, float] = {
        "security.score": clamp(ctx.security_score / 100.0),
        "security.approved": 1.0 if ctx.security_approved else 0.0,
    }
    for name, score in ctx.security_sub_scores.items():
        values[f"security.sub.{name}"] = clamp(score / 100.0)

    smart = float(ctx.smart_money_count)
    dumb = float(ctx.dumb_money_count)
    total = smart + dumb
    if total > 0.0 or ctx.wallets_observed > 0:
        denom = max(total, 1.0)
        values["intel.smart_money_ratio"] = clamp(smart / denom)
        values["intel.dumb_money_ratio"] = clamp(dumb / denom)
        values["intel.smart_pct_supply"] = clamp(
            ctx.smart_money_pct_supply / _SMART_SUPPLY_SATURATION
        )
        values["intel.avg_trust"] = clamp(ctx.avg_wallet_trust / 100.0)
        values["intel.avg_risk"] = clamp(ctx.avg_wallet_risk / 100.0)
        values["intel.cluster_pressure"] = clamp(ctx.largest_cluster_pct / _CLUSTER_PCT_SATURATION)
        values["intel.cluster_count"] = clamp(ctx.cluster_count / _CLUSTER_COUNT_SATURATION)
    return values

"""Holder features — counts, activity, concentration and growth."""

from __future__ import annotations

from hades.contexts.features.domain.models import FeatureInputs


class HolderFeatures:
    """Holder counts, active/recurring wallets, concentration and growth."""

    @property
    def namespace(self) -> str:
        return "holders"

    def compute(self, inputs: FeatureInputs) -> dict[str, float]:
        h = inputs.holders
        if h is None:
            return {
                "count": 0.0,
                "new_holders": 0.0,
                "active_wallets": 0.0,
                "recurring_wallets": 0.0,
                "top10_share_pct": 0.0,
                "gini": 0.0,
                "growth_pct": 0.0,
                "recurring_ratio": 0.0,
                "has_holders": 0.0,
            }
        growth = (h.count - h.prev_count) / h.prev_count if h.prev_count else 0.0
        recurring_ratio = h.recurring_wallets / h.count if h.count else 0.0
        return {
            "count": float(h.count),
            "new_holders": float(h.new_holders),
            "active_wallets": float(h.active_wallets),
            "recurring_wallets": float(h.recurring_wallets),
            "top10_share_pct": h.top10_share_pct,
            "gini": h.gini,
            "growth_pct": growth,
            "recurring_ratio": recurring_ratio,
            "has_holders": 1.0,
        }

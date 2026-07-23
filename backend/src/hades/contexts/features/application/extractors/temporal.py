"""Temporal features — age and time-since-first-event, plus calendar encodings."""

from __future__ import annotations

import math
from datetime import datetime

from hades.contexts.features.domain.models import FeatureInputs


class TemporalFeatures:
    """Exact age, creation hour/day, and time since first swap/holder/pool/liq."""

    @property
    def namespace(self) -> str:
        return "time"

    def compute(self, inputs: FeatureInputs) -> dict[str, float]:
        now = inputs.now
        features: dict[str, float] = {
            "age_exact_seconds": _elapsed(now, inputs.created_at),
            "seconds_since_first_swap": _elapsed(now, inputs.first_swap_at),
            "seconds_since_first_holder": _elapsed(now, inputs.first_holder_at),
            "seconds_since_first_pool": _elapsed(now, inputs.first_pool_at),
            "seconds_since_first_liquidity": _elapsed(now, inputs.first_liquidity_at),
            "utc_hour": float(now.hour),
            "utc_minute": float(now.minute),
            "day_of_week": float(now.weekday()),
            "is_weekend": 1.0 if now.weekday() >= 5 else 0.0,
        }
        if inputs.created_at is not None:
            created = inputs.created_at
            features["creation_hour"] = float(created.hour)
            features["creation_day_of_week"] = float(created.weekday())
            # Cyclical encodings so models see the wrap-around of hour/day.
            features["creation_hour_sin"] = math.sin(2 * math.pi * created.hour / 24.0)
            features["creation_hour_cos"] = math.cos(2 * math.pi * created.hour / 24.0)
        return features


def _elapsed(now: datetime, since: datetime | None) -> float:
    if since is None:
        return 0.0
    return max(0.0, (now - since).total_seconds())

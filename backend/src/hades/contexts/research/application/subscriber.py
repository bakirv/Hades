"""Research subscriber — drives shadow strategies from the live feature stream.

Reacts to ``FeaturesComputed`` (the same event production strategies would see) and
feeds each shadow strategy the observation, so a shadow behaves exactly like a real
strategy on live data — except every trade it takes is virtual. It opens/updates
virtual positions only; it sends no order, commits no capital, and touches no
Portfolio. Realised P&L is filled in offline by the Backtesting/Replay engines
where forward returns exist; live, this measures how often each strategy *fires*.

Handling a live event must never disrupt the pipeline, so every failure is caught
and logged.
"""

from __future__ import annotations

from hades.contexts.features.domain.events import FeaturesComputed
from hades.contexts.features.domain.models import FeatureSet
from hades.contexts.research.application.shadow import ShadowStrategyRunner
from hades.contexts.research.domain.models import ShadowStrategy, clamp01
from hades.contexts.research.domain.ports import HistoricalSample
from hades.shared_kernel.domain.events import DomainEvent
from hades.shared_kernel.logging import get_logger

_logger = get_logger("research.subscriber")

# Maps the lab's normalised channels to candidate Feature-Engine feature names.
# The first name that exists on the vector wins; missing channels stay neutral.
CHANNEL_ALIASES: dict[str, tuple[str, ...]] = {
    "momentum": ("momentum", "price_momentum", "roc"),
    "price_change": ("price_change_pct", "price_change", "pct_change"),
    "rsi": ("rsi", "rsi_14"),
    "liquidity": ("liquidity_score", "liquidity_usd_norm", "liquidity"),
    "volume": ("volume_score", "volume_norm", "volume"),
    "smart_money": ("smart_money_score", "smart_money"),
    "wallet_quality": ("wallet_quality", "holder_quality"),
    "wallet_rotation": ("wallet_rotation", "turnover"),
    "holder_growth": ("holder_growth", "holders_delta"),
    "freshness": ("freshness", "age_inverse", "newness"),
    "news": ("news_score", "news"),
    "social": ("social_score", "social", "social_momentum"),
    "order_flow_imbalance": ("order_flow_imbalance", "ofi", "buy_pressure"),
    "spread": ("spread", "spread_bps_norm"),
    "depth": ("depth", "book_depth", "liquidity_depth"),
}


def sample_from_features(features: FeatureSet, mint: str) -> HistoricalSample:
    """Project a live feature vector onto the lab's normalised channels."""
    sample: HistoricalSample = HistoricalSample({"mint": mint})
    for channel, aliases in CHANNEL_ALIASES.items():
        for name in aliases:
            if name in features.values:
                sample[channel] = clamp01(float(features.values[name]))
                break
    return sample


class ResearchShadowHandler:
    """Owns the live shadow runners and updates them on each FeaturesComputed."""

    def __init__(self, shadows: list[ShadowStrategy]) -> None:
        self._runners = [ShadowStrategyRunner(s) for s in shadows]

    @property
    def shadows(self) -> tuple[ShadowStrategy, ...]:
        return tuple(r.shadow for r in self._runners)

    async def on_features_computed(self, event: DomainEvent) -> None:
        if not isinstance(event, FeaturesComputed):
            return
        try:
            sample = sample_from_features(event.features, str(event.token.mint))
            for runner in self._runners:
                runner.observe(sample)
        except Exception as exc:  # a shadow update must never break the pipeline
            _logger.debug("shadow_update_failed", error=str(exc))

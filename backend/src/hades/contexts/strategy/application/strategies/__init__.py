"""The strategy plugin catalogue.

Every strategy lives in its own module and subclasses
:class:`~hades.contexts.strategy.application.base.BaseStrategy`. Adding a new
strategy is a one-file change plus one line here - the engine, ensemble and
weighting never change. :data:`ALL_STRATEGIES` is the default roster the factory
loads; the registry can add/remove strategies at runtime.
"""

from __future__ import annotations

from hades.contexts.strategy.application.base import BaseStrategy
from hades.contexts.strategy.application.strategies.cross_signal_confirmation import (
    CrossSignalConfirmationStrategy,
)
from hades.contexts.strategy.application.strategies.developer_reputation import (
    DeveloperReputationStrategy,
)
from hades.contexts.strategy.application.strategies.launch_detection import LaunchDetectionStrategy
from hades.contexts.strategy.application.strategies.liquidity_expansion import (
    LiquidityExpansionStrategy,
)
from hades.contexts.strategy.application.strategies.liquidity_rotation import (
    LiquidityRotationStrategy,
)
from hades.contexts.strategy.application.strategies.market_microstructure import (
    MarketMicrostructureStrategy,
)
from hades.contexts.strategy.application.strategies.mean_reversion import MeanReversionStrategy
from hades.contexts.strategy.application.strategies.momentum_breakout import (
    MomentumBreakoutStrategy,
)
from hades.contexts.strategy.application.strategies.narrative_momentum import (
    NarrativeMomentumStrategy,
)
from hades.contexts.strategy.application.strategies.order_flow_imbalance import (
    OrderFlowImbalanceStrategy,
)
from hades.contexts.strategy.application.strategies.smart_money_follow import (
    SmartMoneyFollowStrategy,
)
from hades.contexts.strategy.application.strategies.volatility_compression import (
    VolatilityCompressionStrategy,
)
from hades.contexts.strategy.application.strategies.volume_expansion import VolumeExpansionStrategy
from hades.contexts.strategy.application.strategies.wallet_rotation import WalletRotationStrategy
from hades.contexts.strategy.application.strategies.whale_tracking import WhaleTrackingStrategy

#: Every strategy type shipped with Hades, in a stable declaration order.
STRATEGY_TYPES: tuple[type[BaseStrategy], ...] = (
    MomentumBreakoutStrategy,
    LiquidityExpansionStrategy,
    SmartMoneyFollowStrategy,
    WhaleTrackingStrategy,
    LaunchDetectionStrategy,
    VolumeExpansionStrategy,
    MarketMicrostructureStrategy,
    MeanReversionStrategy,
    VolatilityCompressionStrategy,
    LiquidityRotationStrategy,
    NarrativeMomentumStrategy,
    DeveloperReputationStrategy,
    WalletRotationStrategy,
    OrderFlowImbalanceStrategy,
    CrossSignalConfirmationStrategy,
)


def default_strategies() -> list[BaseStrategy]:
    """Instantiate one of every shipped strategy (fresh, unconfigured)."""
    return [cls() for cls in STRATEGY_TYPES]


__all__ = [
    "STRATEGY_TYPES",
    "CrossSignalConfirmationStrategy",
    "DeveloperReputationStrategy",
    "LaunchDetectionStrategy",
    "LiquidityExpansionStrategy",
    "LiquidityRotationStrategy",
    "MarketMicrostructureStrategy",
    "MeanReversionStrategy",
    "MomentumBreakoutStrategy",
    "NarrativeMomentumStrategy",
    "OrderFlowImbalanceStrategy",
    "SmartMoneyFollowStrategy",
    "VolatilityCompressionStrategy",
    "VolumeExpansionStrategy",
    "WalletRotationStrategy",
    "WhaleTrackingStrategy",
    "default_strategies",
]

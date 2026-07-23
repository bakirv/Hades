"""Factory - assembles a fully-wired Strategy Engine from settings.

Construction in one place: it loads the default strategy roster, applies operator
configuration (global + per-strategy parameters, force-disables) purely from
settings, and wires the registry, dynamic-weighting engine, ensemble builder,
self-evaluator and lifecycle into a ready-to-run :class:`StrategyEngine`. Tests
build a real engine in one call.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hades.contexts.notification.application.publisher import NotificationPublisher
from hades.contexts.strategy.application.base import BaseStrategy
from hades.contexts.strategy.application.context_builder import MarketContextBuilder
from hades.contexts.strategy.application.engine import StrategyEngine
from hades.contexts.strategy.application.ensemble import EnsembleBuilder
from hades.contexts.strategy.application.evaluation import SelfEvaluator
from hades.contexts.strategy.application.lifecycle import ShadowLifecycle
from hades.contexts.strategy.application.metrics import StrategyMetrics
from hades.contexts.strategy.application.registry import StrategyRegistry
from hades.contexts.strategy.application.strategies import default_strategies
from hades.contexts.strategy.application.weighting import DynamicWeightEngine
from hades.contexts.strategy.domain.ports import (
    PerformanceStore,
    SignalStore,
    StrategyFactsPort,
)
from hades.shared_kernel.config import Settings
from hades.shared_kernel.events import EventBus


@dataclass
class StrategyEngineBundle:
    """The wired Strategy Engine plus the collaborators the runtime/API need."""

    engine: StrategyEngine
    registry: StrategyRegistry
    context_builder: MarketContextBuilder
    lifecycle: ShadowLifecycle


def build_strategy_engine(
    settings: Settings,
    *,
    event_bus: EventBus | None = None,
    notifier: NotificationPublisher | None = None,
    metrics: StrategyMetrics | None = None,
    performance_store: PerformanceStore | None = None,
    signal_store: SignalStore | None = None,
    facts: StrategyFactsPort | None = None,
    strategies: list[BaseStrategy] | None = None,
) -> StrategyEngineBundle:
    """Wire the whole Strategy Engine from configuration."""
    cfg = settings.strategy
    registry = StrategyRegistry(error_threshold=cfg.error_threshold)
    roster = strategies if strategies is not None else default_strategies()
    per_strategy = cfg.per_strategy
    disabled = cfg.disabled_list

    for strategy in roster:
        registry.register(strategy)
        params: dict[str, Any] = {"sensitivity": cfg.sensitivity}
        params.update(per_strategy.get(strategy.name, {}))
        if strategy.name in disabled:
            params["enabled"] = False
        if not cfg.shadow_enabled and not strategy.metadata.is_production:
            params["enabled"] = False
        strategy.load_configuration(params)

    lifecycle = ShadowLifecycle()
    engine = StrategyEngine(
        registry=registry,
        weighting=DynamicWeightEngine(weight_floor=cfg.weight_floor),
        ensemble=EnsembleBuilder(decision_deadband=cfg.decision_deadband),
        evaluator=SelfEvaluator(),
        lifecycle=lifecycle,
        event_bus=event_bus,
        notifier=notifier,
        metrics=metrics,
        performance_store=performance_store,
        signal_store=signal_store,
        min_notify_confidence=cfg.min_notify_confidence,
        research_boost=cfg.research_boost,
    )
    context_builder = MarketContextBuilder(facts=facts)
    return StrategyEngineBundle(
        engine=engine,
        registry=registry,
        context_builder=context_builder,
        lifecycle=lifecycle,
    )

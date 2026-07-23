"""Candidate strategy library + a pure genome evaluator.

Each of the ten archetypes the spec calls for (Momentum, Mean Reversion,
Liquidity Breakout, Smart Money Follow, Wallet Rotation, Launch Detection, News
Driven, Social Momentum, Order Flow, Microstructure) is expressed as a pure
signal function over a feature vector — never as executable trading code. A
:class:`StrategyGenome` binds an archetype to thresholds/weights; the evaluator
blends the archetype signal with the genome and decides whether to open a
*virtual* trade.

There is no path from here to an order. Evaluating a strategy produces a
:class:`TradeRecord`, which is scored offline — nothing more.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta

from hades.contexts.research.domain.models import (
    CandidateStrategy,
    StrategyArchetype,
    StrategyGenome,
    TradeRecord,
    clamp01,
    safe_div,
)
from hades.contexts.research.domain.ports import HistoricalSample

Feature = dict[str, float]

# The representative feature keys the archetypes read. The dataset builder maps
# the Feature Engine's ~100 features onto these normalised (0..1) channels; a
# missing key defaults to a neutral 0.5 so a strategy degrades gracefully.
_NEUTRAL = 0.5


def _f(sample: HistoricalSample, key: str, default: float = _NEUTRAL) -> float:
    value = sample.get(key, default)
    try:
        return clamp01(float(value))
    except (TypeError, ValueError):
        return default


# --- archetype signal functions (pure) ---------------------------------------


def _momentum(s: HistoricalSample) -> float:
    return clamp01(0.6 * _f(s, "momentum") + 0.4 * _f(s, "price_change"))


def _mean_reversion(s: HistoricalSample) -> float:
    # Buy weakness: a low RSI / oversold reading is a strong signal.
    return clamp01(0.7 * (1.0 - _f(s, "rsi")) + 0.3 * (1.0 - _f(s, "price_change")))


def _liquidity_breakout(s: HistoricalSample) -> float:
    return clamp01(0.5 * _f(s, "liquidity") + 0.5 * _f(s, "volume"))


def _smart_money_follow(s: HistoricalSample) -> float:
    return clamp01(0.7 * _f(s, "smart_money") + 0.3 * _f(s, "wallet_quality"))


def _wallet_rotation(s: HistoricalSample) -> float:
    return clamp01(0.6 * _f(s, "wallet_rotation") + 0.4 * _f(s, "holder_growth"))


def _launch_detection(s: HistoricalSample) -> float:
    # Fresh launches: young age + rising liquidity.
    return clamp01(0.6 * _f(s, "freshness") + 0.4 * _f(s, "liquidity"))


def _news_driven(s: HistoricalSample) -> float:
    return clamp01(0.6 * _f(s, "news") + 0.4 * _f(s, "volume"))


def _social_momentum(s: HistoricalSample) -> float:
    return clamp01(0.7 * _f(s, "social") + 0.3 * _f(s, "momentum"))


def _order_flow(s: HistoricalSample) -> float:
    return clamp01(0.7 * _f(s, "order_flow_imbalance") + 0.3 * _f(s, "volume"))


def _microstructure(s: HistoricalSample) -> float:
    # Tight spread + healthy depth.
    return clamp01(0.5 * (1.0 - _f(s, "spread")) + 0.5 * _f(s, "depth"))


_SIGNALS: dict[StrategyArchetype, Callable[[HistoricalSample], float]] = {
    StrategyArchetype.MOMENTUM: _momentum,
    StrategyArchetype.MEAN_REVERSION: _mean_reversion,
    StrategyArchetype.LIQUIDITY_BREAKOUT: _liquidity_breakout,
    StrategyArchetype.SMART_MONEY_FOLLOW: _smart_money_follow,
    StrategyArchetype.WALLET_ROTATION: _wallet_rotation,
    StrategyArchetype.LAUNCH_DETECTION: _launch_detection,
    StrategyArchetype.NEWS_DRIVEN: _news_driven,
    StrategyArchetype.SOCIAL_MOMENTUM: _social_momentum,
    StrategyArchetype.ORDER_FLOW: _order_flow,
    StrategyArchetype.MICROSTRUCTURE: _microstructure,
}


def archetype_signal(archetype: StrategyArchetype, sample: HistoricalSample) -> float:
    """The pure archetype signal in [0,1] for a sample."""
    return _SIGNALS[archetype](sample)


# --- genome evaluation -------------------------------------------------------


def score_sample(genome: StrategyGenome, sample: HistoricalSample) -> float:
    """Blend the archetype signal with the genome's confirming thresholds.

    Each configured threshold acts as a soft gate: features above their threshold
    reinforce the entry, below dampen it. The result is a single 0..1 conviction.
    """
    base = archetype_signal(genome.archetype, sample)
    if not genome.thresholds:
        return clamp01(base)
    confirmations = 0.0
    weight_sum = 0.0
    for key, threshold in genome.thresholds.items():
        w = genome.weights.get(key, 1.0)
        weight_sum += w
        confirmations += w * (1.0 if _f(sample, key) >= threshold else 0.0)
    confirm_ratio = safe_div(confirmations, weight_sum, default=1.0)
    return clamp01(0.6 * base + 0.4 * confirm_ratio)


def _realised_return(genome: StrategyGenome, sample: HistoricalSample) -> float:
    """Cap a sample's forward return by the genome's TP/SL — a virtual exit."""
    fwd = float(sample.get("forward_return", 0.0))
    if fwd >= genome.take_profit:
        return genome.take_profit
    if fwd <= -genome.stop_loss:
        return -genome.stop_loss
    return fwd


def evaluate(
    genome: StrategyGenome, samples: Sequence[HistoricalSample]
) -> tuple[TradeRecord, ...]:
    """Run a genome over samples, opening a virtual trade whenever conviction
    clears the entry score. Deterministic and side-effect free."""
    base = datetime(2020, 1, 1, tzinfo=UTC)
    trades: list[TradeRecord] = []
    for i, sample in enumerate(samples):
        conviction = score_sample(genome, sample)
        if conviction < genome.entry_score:
            continue
        ret = _realised_return(genome, sample)
        opened = base + timedelta(seconds=i)
        hold = min(genome.max_holding_seconds, float(sample.get("holding_seconds", 300.0)))
        trades.append(
            TradeRecord(
                opened_at=opened,
                closed_at=opened + timedelta(seconds=hold),
                ret=ret,
                holding_seconds=hold,
                mint=str(sample.get("mint", "")) or None,
                reason=f"{genome.archetype.value}@{conviction:.2f}",
            )
        )
    return tuple(trades)


# --- default genomes ---------------------------------------------------------


def default_genome(archetype: StrategyArchetype) -> StrategyGenome:
    """A sensible starting genome for an archetype (the optimiser refines it)."""
    return StrategyGenome(
        archetype=archetype,
        thresholds={"liquidity": 0.4, "volume": 0.4},
        weights={"liquidity": 1.0, "volume": 1.0},
        entry_score=0.6,
        take_profit=0.30,
        stop_loss=0.15,
        max_holding_seconds=3600.0,
    )


def default_candidates() -> tuple[CandidateStrategy, ...]:
    """One candidate per archetype — the lab's starting research population."""
    return tuple(
        CandidateStrategy(
            name=archetype.value,
            archetype=archetype,
            genome=default_genome(archetype),
        )
        for archetype in StrategyArchetype
    )

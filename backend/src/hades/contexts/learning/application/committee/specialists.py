"""The twelve committee specialists — their questions, features and priors.

Each :class:`SpecialistSpec` declares one analyst: the narrow question it answers,
the features it looks at, and *documented default weights* so the committee is
meaningful before any training run. Positive weights push the probability up,
negative down; the Training Engine may later refit them into a new registry
version without touching this file.

Two feature families feed the specialists:

* **Feature-engine features** (``basic.*``, ``tech.*``, ``holders.*`` …) —
  normalised by the Feature Store's :class:`FeatureNormalizer`.
* **Context features** (``security.*``, ``intel.*``) — the upstream Security
  verdict and Wallet-Intelligence snapshot, injected as pre-normalised [0,1]
  values by the committee manager. See :mod:`context_features`.
"""

from __future__ import annotations

from hades.contexts.learning.application.committee.base import (
    ReasonTemplate,
    SpecialistModel,
    SpecialistSpec,
)
from hades.contexts.learning.domain.models import CommitteeMember

_M = CommitteeMember

# A shared library of human phrasings, reused across specialists.
_TEMPLATES: dict[str, ReasonTemplate] = {
    "basic.liquidity": ReasonTemplate("basic.liquidity", "deep liquidity", "thin liquidity"),
    "pool.depth_usd": ReasonTemplate("pool.depth_usd", "solid book depth", "shallow book depth"),
    "basic.liquidity_to_mcap": ReasonTemplate(
        "basic.liquidity_to_mcap", "cap well backed by liquidity", "cap thinly backed"
    ),
    "basic.spread_bps": ReasonTemplate("basic.spread_bps", "wide spread", "tight spread"),
    "basic.slippage_bps": ReasonTemplate("basic.slippage_bps", "high slippage", "low slippage"),
    "pool.liquidity_change_pct": ReasonTemplate(
        "pool.liquidity_change_pct", "liquidity growing", "liquidity draining"
    ),
    "pool.lp_locked": ReasonTemplate("pool.lp_locked", "LP locked", "LP unlocked"),
    "basic.volume_to_liquidity": ReasonTemplate(
        "basic.volume_to_liquidity", "healthy turnover", "low turnover"
    ),
    "tech.price_slope": ReasonTemplate(
        "tech.price_slope", "price trending up", "price trending down"
    ),
    "tech.macd": ReasonTemplate("tech.macd", "MACD positive", "MACD negative"),
    "tech.trend_alignment": ReasonTemplate(
        "tech.trend_alignment", "trends aligned up", "trends conflicting"
    ),
    "regime.macro_trend": ReasonTemplate(
        "regime.macro_trend", "macro trend up", "macro trend down"
    ),
    "regime.micro_trend": ReasonTemplate(
        "regime.micro_trend", "micro trend up", "micro trend down"
    ),
    "basic.buyer_seller_ratio": ReasonTemplate(
        "basic.buyer_seller_ratio", "buyers dominate", "sellers dominate"
    ),
    "basic.buy_sell_volume_ratio": ReasonTemplate(
        "basic.buy_sell_volume_ratio", "buy volume leads", "sell volume leads"
    ),
    "tech.volume_slope": ReasonTemplate("tech.volume_slope", "volume rising", "volume fading"),
    "holders.holders_growth_pct": ReasonTemplate(
        "holders.holders_growth_pct", "holders growing", "holders shrinking"
    ),
    "tech.volatility": ReasonTemplate("tech.volatility", "high volatility", "calm volatility"),
    "tech.volatility_explosion": ReasonTemplate(
        "tech.volatility_explosion", "volatility expanding", "volatility contained"
    ),
    "tech.volatility_compression": ReasonTemplate(
        "tech.volatility_compression", "coiled (compressed) volatility", "no compression"
    ),
    "tech.atr_14": ReasonTemplate("tech.atr_14", "wide ATR range", "narrow ATR range"),
    "tech.rsi_14": ReasonTemplate("tech.rsi_14", "RSI overbought", "RSI oversold/neutral"),
    "basic.market_cap": ReasonTemplate("basic.market_cap", "larger cap", "micro cap"),
    "holders.count": ReasonTemplate("holders.count", "broad holder base", "few holders"),
    "holders.top10_share_pct": ReasonTemplate(
        "holders.top10_share_pct", "top-10 concentration high", "top-10 concentration low"
    ),
    "holders.gini": ReasonTemplate("holders.gini", "supply concentrated", "supply well spread"),
    "holders.recurring_ratio": ReasonTemplate(
        "holders.recurring_ratio", "many recurring holders", "mostly one-off wallets"
    ),
    "basic.age_minutes": ReasonTemplate(
        "basic.age_minutes", "more established age", "very new token"
    ),
    "basic.trades_5m": ReasonTemplate("basic.trades_5m", "active 5m flow", "quiet 5m flow"),
    "basic.trades_1h": ReasonTemplate("basic.trades_1h", "active hourly flow", "quiet hourly flow"),
    "time.utc_hour": ReasonTemplate("time.utc_hour", "later session hour", "earlier session hour"),
    # context features
    "security.score": ReasonTemplate(
        "security.score", "strong security score", "weak security score"
    ),
    "security.approved": ReasonTemplate(
        "security.approved", "cleared the security gate", "not cleared by security"
    ),
    "security.sub.contract": ReasonTemplate(
        "security.sub.contract", "clean contract", "contract concerns"
    ),
    "security.sub.authority": ReasonTemplate(
        "security.sub.authority", "authorities renounced/safe", "risky authorities"
    ),
    "security.sub.honeypot": ReasonTemplate(
        "security.sub.honeypot", "not a honeypot", "honeypot risk"
    ),
    "security.sub.liquidity": ReasonTemplate(
        "security.sub.liquidity", "secure liquidity", "insecure liquidity"
    ),
    "security.sub.developer": ReasonTemplate(
        "security.sub.developer", "reputable developer", "risky developer"
    ),
    "security.sub.wallet_cluster": ReasonTemplate(
        "security.sub.wallet_cluster", "no coordinated clusters", "coordinated clusters present"
    ),
    "security.sub.rug_pull": ReasonTemplate(
        "security.sub.rug_pull", "low rug-pull risk", "elevated rug-pull risk"
    ),
    "security.sub.behavior": ReasonTemplate(
        "security.sub.behavior", "organic behaviour", "manipulative behaviour"
    ),
    "intel.smart_money_ratio": ReasonTemplate(
        "intel.smart_money_ratio", "smart money present", "little smart money"
    ),
    "intel.smart_pct_supply": ReasonTemplate(
        "intel.smart_pct_supply", "smart money holds supply", "smart money holds little"
    ),
    "intel.dumb_money_ratio": ReasonTemplate(
        "intel.dumb_money_ratio", "dumb money crowded", "little dumb money"
    ),
    "intel.avg_trust": ReasonTemplate("intel.avg_trust", "trusted wallets", "low-trust wallets"),
    "intel.avg_risk": ReasonTemplate("intel.avg_risk", "risky wallets", "low-risk wallets"),
    "intel.cluster_pressure": ReasonTemplate(
        "intel.cluster_pressure", "large coordinated cluster", "no cluster pressure"
    ),
}


def _tpl(*names: str) -> tuple[ReasonTemplate, ...]:
    return tuple(_TEMPLATES[n] for n in names if n in _TEMPLATES)


_SPECS: tuple[SpecialistSpec, ...] = (
    SpecialistSpec(
        member=_M.LIQUIDITY,
        question="Is liquidity healthy?",
        default_bias=-0.4,
        default_weights={
            "basic.liquidity": 1.8,
            "pool.depth_usd": 1.2,
            "basic.liquidity_to_mcap": 1.0,
            "pool.liquidity_change_pct": 0.6,
            "basic.spread_bps": -1.4,
            "basic.slippage_bps": -1.2,
            "basic.volume_to_liquidity": 0.4,
            "holders.count": 0.5,
        },
        reason_templates=_tpl(
            "basic.liquidity",
            "pool.depth_usd",
            "basic.liquidity_to_mcap",
            "pool.liquidity_change_pct",
            "basic.spread_bps",
            "basic.slippage_bps",
            "basic.volume_to_liquidity",
            "holders.count",
        ),
    ),
    SpecialistSpec(
        member=_M.MOMENTUM,
        question="Is momentum positive?",
        default_bias=-0.6,
        default_weights={
            "tech.price_slope": 1.4,
            "tech.trend_alignment": 1.2,
            "basic.buyer_seller_ratio": 0.9,
            "tech.macd": 0.8,
            "regime.macro_trend": 0.8,
            "holders.holders_growth_pct": 0.7,
            "basic.buy_sell_volume_ratio": 0.7,
            "tech.volume_slope": 0.6,
            "tech.volatility_explosion": 0.5,
            "tech.rsi_14": 0.4,
            "basic.trades_5m": 0.3,
        },
        reason_templates=_tpl(
            "tech.price_slope",
            "tech.trend_alignment",
            "basic.buyer_seller_ratio",
            "tech.macd",
            "regime.macro_trend",
            "holders.holders_growth_pct",
            "basic.buy_sell_volume_ratio",
            "tech.volume_slope",
            "tech.volatility_explosion",
            "tech.rsi_14",
            "basic.trades_5m",
        ),
    ),
    SpecialistSpec(
        member=_M.VOLATILITY,
        question="Is volatility favourable?",
        default_bias=0.8,
        default_weights={
            "tech.volatility": -1.6,
            "tech.volatility_compression": 1.0,
            "tech.volatility_explosion": -0.8,
            "tech.atr_14": -0.5,
        },
        reason_templates=_tpl(
            "tech.volatility",
            "tech.volatility_compression",
            "tech.volatility_explosion",
            "tech.atr_14",
        ),
        min_coverage=0.5,
    ),
    SpecialistSpec(
        member=_M.MARKET_REGIME,
        question="Is the market regime constructive?",
        default_bias=-0.3,
        default_weights={
            "regime.macro_trend": 1.3,
            "tech.trend_alignment": 0.9,
            "regime.micro_trend": 0.8,
            "tech.price_slope": 0.7,
            "basic.liquidity": 0.6,
            "basic.liquidity_to_mcap": 0.5,
            "basic.market_cap": 0.4,
            "tech.volatility": -0.8,
        },
        reason_templates=_tpl(
            "regime.macro_trend",
            "tech.trend_alignment",
            "regime.micro_trend",
            "tech.price_slope",
            "basic.liquidity",
            "basic.market_cap",
            "tech.volatility",
        ),
    ),
    SpecialistSpec(
        member=_M.WALLET,
        question="Is wallet intelligence positive?",
        default_bias=-0.3,
        default_weights={
            "intel.smart_money_ratio": 1.6,
            "intel.smart_pct_supply": 1.2,
            "intel.dumb_money_ratio": -1.1,
            "intel.avg_trust": 1.0,
            "intel.avg_risk": -1.0,
        },
        reason_templates=_tpl(
            "intel.smart_money_ratio",
            "intel.smart_pct_supply",
            "intel.dumb_money_ratio",
            "intel.avg_trust",
            "intel.avg_risk",
        ),
        min_coverage=0.2,
    ),
    SpecialistSpec(
        member=_M.SECURITY,
        question="Is the token secure?",
        default_bias=-0.5,
        default_weights={
            "security.score": 2.0,
            "security.approved": 1.0,
            "security.sub.honeypot": 0.8,
            "security.sub.contract": 0.6,
            "security.sub.authority": 0.6,
            "security.sub.liquidity": 0.4,
        },
        reason_templates=_tpl(
            "security.score",
            "security.approved",
            "security.sub.honeypot",
            "security.sub.contract",
            "security.sub.authority",
            "security.sub.liquidity",
        ),
        min_coverage=0.2,
    ),
    SpecialistSpec(
        member=_M.HOLDER_DISTRIBUTION,
        question="Is holder distribution healthy?",
        default_bias=0.2,
        default_weights={
            "holders.top10_share_pct": -1.5,
            "holders.gini": -1.2,
            "holders.count": 1.0,
            "holders.recurring_ratio": 0.8,
            "holders.holders_growth_pct": 0.6,
        },
        reason_templates=_tpl(
            "holders.top10_share_pct",
            "holders.gini",
            "holders.count",
            "holders.recurring_ratio",
            "holders.holders_growth_pct",
        ),
    ),
    SpecialistSpec(
        member=_M.DEVELOPER,
        question="Is the developer trustworthy?",
        default_bias=-0.3,
        default_weights={
            "security.sub.developer": 1.8,
            "security.sub.rug_pull": 1.0,
            "security.sub.wallet_cluster": 0.8,
            "pool.lp_locked": 0.6,
            "intel.avg_trust": 0.5,
        },
        reason_templates=_tpl(
            "security.sub.developer",
            "security.sub.rug_pull",
            "security.sub.wallet_cluster",
            "pool.lp_locked",
            "intel.avg_trust",
        ),
        min_coverage=0.2,
    ),
    SpecialistSpec(
        member=_M.BEHAVIOR,
        question="Is trading behaviour organic?",
        default_bias=0.1,
        default_weights={
            "security.sub.behavior": 0.8,
            "holders.recurring_ratio": 0.9,
            "intel.smart_money_ratio": 0.9,
            "intel.dumb_money_ratio": -0.8,
            "intel.cluster_pressure": -0.9,
            "basic.buyer_seller_ratio": 0.5,
        },
        reason_templates=_tpl(
            "security.sub.behavior",
            "holders.recurring_ratio",
            "intel.smart_money_ratio",
            "intel.dumb_money_ratio",
            "intel.cluster_pressure",
            "basic.buyer_seller_ratio",
        ),
        min_coverage=0.2,
    ),
    SpecialistSpec(
        member=_M.RISK,
        question="How contained is the downside risk?",
        default_bias=0.2,
        default_weights={
            "security.sub.rug_pull": 1.2,
            "intel.cluster_pressure": -1.0,
            "holders.top10_share_pct": -1.2,
            "pool.lp_locked": 0.9,
            "tech.volatility": -0.9,
            "holders.gini": -0.9,
            "security.sub.contract": 0.8,
            "intel.avg_risk": -0.8,
            "security.sub.authority": 0.7,
            "basic.liquidity_to_mcap": 0.6,
            "basic.age_minutes": 0.4,
        },
        reason_templates=_tpl(
            "security.sub.rug_pull",
            "intel.cluster_pressure",
            "holders.top10_share_pct",
            "pool.lp_locked",
            "tech.volatility",
            "holders.gini",
            "security.sub.contract",
            "intel.avg_risk",
            "security.sub.authority",
            "basic.liquidity_to_mcap",
            "basic.age_minutes",
        ),
    ),
    SpecialistSpec(
        member=_M.TIMING,
        question="Is this a favourable entry moment?",
        default_bias=0.1,
        default_weights={
            "tech.volatility_compression": 1.0,
            "regime.micro_trend": 0.9,
            "tech.trend_alignment": 0.7,
            "basic.trades_5m": 0.5,
            "tech.rsi_14": -0.5,
            "basic.age_minutes": -0.4,
            "time.utc_hour": 0.1,
        },
        reason_templates=_tpl(
            "tech.volatility_compression",
            "regime.micro_trend",
            "tech.trend_alignment",
            "basic.trades_5m",
            "tech.rsi_14",
            "basic.age_minutes",
            "time.utc_hour",
        ),
    ),
    SpecialistSpec(
        member=_M.MICROSTRUCTURE,
        question="Is order-flow microstructure healthy?",
        default_bias=-0.2,
        default_weights={
            "basic.spread_bps": -1.3,
            "basic.slippage_bps": -1.1,
            "pool.depth_usd": 1.0,
            "basic.buy_sell_volume_ratio": 0.7,
            "basic.trades_1h": 0.6,
            "tech.volume_slope": 0.5,
            "basic.volume_to_liquidity": 0.5,
            "basic.trades_5m": 0.4,
        },
        reason_templates=_tpl(
            "basic.spread_bps",
            "basic.slippage_bps",
            "pool.depth_usd",
            "basic.buy_sell_volume_ratio",
            "basic.trades_1h",
            "tech.volume_slope",
            "basic.volume_to_liquidity",
            "basic.trades_5m",
        ),
    ),
)

#: The specialist specs keyed by member, for the registry/training to introspect.
SPECIALIST_SPECS: dict[CommitteeMember, SpecialistSpec] = {s.member: s for s in _SPECS}


def default_specialists() -> tuple[SpecialistModel, ...]:
    """Build the full committee from documented defaults (no training needed)."""
    return tuple(SpecialistModel.from_defaults(spec) for spec in _SPECS)

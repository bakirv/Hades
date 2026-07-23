"""Strategy Engine context - the modular set of quantitative strategies.

Responsibility:
    * Host every trading strategy as an independent, hot-swappable plugin behind
      one interface (:class:`~hades.contexts.strategy.domain.ports.Strategy`).
    * Turn the AI Committee's explainable verdict (``CommitteePredictionGenerated``)
      into per-strategy :class:`StrategySignal`s and a single, weighted
      :class:`EnsembleSignal` - never a simple vote.
    * Weight each strategy dynamically by market regime, recent quality and the
      AI's confidence; evaluate each one continuously and taper (never delete) a
      degrading strategy's weight.
    * Progress new strategies through the Research -> Backtest -> Replay -> Paper ->
      Shadow -> Production ladder; never skip a stage.

Critical design rule (the platform-wide invariant): **strategies never execute
orders, never modify positions and never bypass the Risk Manager.** They only
*detect opportunities* and explain them. The decision flow is always:

    scanner -> features -> security -> wallet -> committee -> **strategy** -> risk
        -> execution -> portfolio

Everything here is pure and I/O-free: a strategy reads a :class:`MarketContext`
value object (assembled by infrastructure from the committee verdict) and returns
a signal. It never touches the database or the Execution Engine.
"""

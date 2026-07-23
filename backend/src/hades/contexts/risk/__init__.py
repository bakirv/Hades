"""Risk Manager context — the sole decision authority.

Responsibility:
    * Consume the probabilistic ``ScoreResult`` and the current portfolio state.
    * Apply hard risk policy: exposure caps, concurrent-position limits, per-trade
      sizing, daily loss limits, black/white lists, the kill switch.
    * Turn a probability into an action: approve a sized trade or reject with a
      reason. Position sizing is a risk decision (e.g. Kelly-capped), not a model
      output.
    * Emit ``TradeApproved`` or ``TradeRejected``.

If Scoring is the brain, Risk is the executive function. Nothing reaches the
Execution Engine without passing here.

Phase 1 scope: contracts only.
"""

"""Market Engine context — live market state for tokens under consideration.

Responsibility:
    * Provide price, liquidity, volume, spread and OHLCV for a token, both as a
      point-in-time snapshot (for scoring) and as a live stream (for managing
      open positions: trailing stops, take-profit, stop-loss triggers).
    * Normalise data across venues (Raydium, Orca, Jupiter routes).
    * Emit ``MarketSnapshotUpdated`` and price-tick events.

Phase 1 scope: contracts only.
"""

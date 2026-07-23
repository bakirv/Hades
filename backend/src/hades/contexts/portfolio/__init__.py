"""Portfolio Manager context — the book of record for positions and exposure.

Responsibility:
    * Own the ``Position`` aggregate lifecycle: open → update (price, trailing
      stop) → close.
    * Track aggregate exposure, realised/unrealised PnL, and per-token holdings.
    * Serve the read model the Risk Manager consults before approving trades.
    * Emit ``PositionOpened``, ``PositionUpdated``, ``TrailingStopAdjusted``,
      ``PositionClosed``.

This is the only context that owns long-lived, event-sourced state. Execution
reports fills to it; it never places orders itself.

Phase 1 scope: the Position aggregate + contracts (behaviour stubs raise until
later phases wire real logic).
"""

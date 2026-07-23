"""Research Lab context — offline quantitative R&D. NEVER touches live trading.

Responsibility:
    * Run backtests, walk-forward and Monte-Carlo experiments over historical
      event data to discover and validate new signals, features and strategies.
    * Work on *copies* of data; it has no path to the Execution Engine.
    * Propose candidates for promotion; promotion is a separate, human-gated,
      fail-closed action.
    * Emit ``ExperimentCompleted``, ``CandidateProposed``.

Hard rule: the Research Lab can never enable live trading or place an order.
This isolation is structural — it depends on read models only, never on
``execution`` ports.

Phase 1 scope: contracts only.
"""

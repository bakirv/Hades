"""Execution Engine context — the ONLY component that differs paper vs live.

Responsibility:
    * Consume ``TradeApproved`` and turn a sized decision into real orders.
    * Manage order lifecycle: submit → confirm → fill (or fail), with slippage,
      priority fees and confirmation timeouts.
    * Report fills back to the Portfolio Manager via events.

Critical design rule ("mismo motor de decisiones"): every context upstream —
scanner, features, security, wallet, market, scoring, risk — is identical in
paper and live mode. Only the :class:`Executor` adapter swaps:
    * ``PaperExecutor`` — deterministic simulation (latency, slippage, rejects).
    * ``LiveExecutor``  — real Solana transactions via the configured signer/RPC.
The adapter is selected at bootstrap from ``settings.is_live``. Live execution is
guarded so a config file alone can never flip the platform into real trading.

Phase 1 scope: contracts only.
"""

"""Wallet Intelligence context — who is behind and around this token?

Responsibility:
    * Profile the deployer and early buyers: history, prior rugs, funding
      lineage, links to known good/bad actors.
    * Detect smart-money and insider clustering; measure holder quality.
    * Produce a normalised ``Score`` (0–100) reflecting wallet-side conviction
      and risk.
    * Emit ``WalletScoreComputed``.

Phase 1 scope: contracts only.
"""

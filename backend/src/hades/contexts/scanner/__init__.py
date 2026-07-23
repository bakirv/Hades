"""Scanner context — continuous discovery of new Solana opportunities.

Responsibility (discovery ONLY — no analysis, no scoring, no opinions):
    * Poll configured sources (pump.fun, Raydium, DexScreener, on-chain logs).
    * Deduplicate and apply coarse gating (min liquidity, max age, black/white
      lists) so obvious noise never enters the pipeline.
    * Emit ``TokenDiscovered`` for every genuinely new candidate.

It knows nothing about features, security or value. It is the mouth of the
funnel; everything downstream reacts to its events.

Phase 1 scope: contracts only (:mod:`domain.events`, :mod:`domain.ports`).
"""

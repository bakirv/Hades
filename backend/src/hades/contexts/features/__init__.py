"""Feature Engine context — turns raw token data into a rich feature vector.

Responsibility:
    * On ``TokenDiscovered``, compute the hundreds of variables that describe a
      token: liquidity dynamics, holder distribution, transaction cadence,
      social/on-chain signals, price microstructure, deployer lineage, etc.
    * Persist features to a feature store (reused by Scoring and, later, the
      Learning Engine — training/serving parity).
    * Emit ``FeaturesComputed``.

It computes facts, not judgements. Whether a feature is "good" is Scoring's job.

Phase 1 scope: contracts only.
"""

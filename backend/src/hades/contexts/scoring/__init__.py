"""Scoring Engine context — the quantitative brain.

Responsibility:
    * Fuse features + security + wallet + market signals into a single, calibrated
      view of a token's opportunity.
    * Output **probabilities and confidences, never decisions.** The canonical
      output is e.g. "P(ROI > 20%) = 0.82, confidence 0.91" plus a composite
      ``Score``. It NEVER says "buy PEPE".
    * Every output is explainable: the contributing signals and model version
      are attached.
    * Emit ``FinalScoreComputed``.

The decision to act belongs exclusively to the Risk Manager downstream. This
separation is a core design rule: the model quantifies, the risk layer decides.

Phase 1 scope: contracts only.
"""

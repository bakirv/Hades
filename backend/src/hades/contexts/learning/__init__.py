"""Learning context — the AI Committee, Hades' explainable quantitative brain.

Responsibility:
    * Run an **AI Committee**: many single-purpose specialist models (liquidity,
      momentum, volatility, market regime, wallet intelligence, security, holder
      distribution, developer, behaviour, risk, timing, microstructure). Each
      emits only a *quantitative opinion* — a probability, a confidence and the
      reasons behind both. None decides.
    * Fuse the opinions with a **Meta Model** into three calibrated probabilities
      (P(ROI positive), P(hit TP), P(hit SL)) plus a multi-factor confidence.
    * Keep the whole thing **explainable, versioned and auditable**: transparent
      linear-logistic models whose weights are data, an append-only Model
      Registry, a Feature Store contract, continuous feature-importance, and a
      Model Monitor that watches for drift.
    * Learn from history — executed *and* rejected opportunities — via the
      Dataset Builder + Training/Validation engines. Promotion is always
      human/policy-gated; a worse model is never deployed.

Hard boundary (identical to every other analytical context): the AI **never**
buys, sells or sizes. It produces probabilities and evidence. The Risk Manager
(a later context) is the only thing allowed to act on a committee prediction.
No trade execution is implemented here.
"""

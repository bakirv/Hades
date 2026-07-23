"""Security Engine context — is this token a trap?

Responsibility:
    * Assess rug/scam risk: mint & freeze authority, LP lock/burn status,
      honeypot simulation, tax/transfer hooks, holder concentration, contract
      red flags.
    * Produce a normalised ``Score`` (0-100) plus a structured list of the
      specific risk flags that drove it (explainability — never a black box).
    * Emit ``SecurityScoreComputed``.

A low security score can veto a candidate regardless of upside. Security is a
guardrail, not an optimiser.

Phase 1 scope: contracts only.
"""

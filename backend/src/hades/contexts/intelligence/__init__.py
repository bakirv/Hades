"""Wallet Intelligence context — the on-chain knowledge base.

This is not a per-token check; it is a *wallet-centric* asset that grows for
years. Every wallet Hades ever observes gets a permanent identity here, and its
history, reputation, behaviour, funding lineage, relationships and influence
accumulate over time. Nothing is ever deleted — a rejected token and a dumb-money
wallet are as valuable to learn from as a winner.

Responsibility:
    * **Registry** — record every wallet seen, forever (first/last seen, activity,
      DEXes, protocols, lifetime).
    * **Profiler / Reputation** — build an evolving, non-binary reputation
      (trust, risk, consistency, experience, profitability) per wallet.
    * **Funding / Relationship / Cluster** — trace who funded whom, build the
      graph, and collapse coordinated wallets into single-entity clusters.
    * **Smart / Dumb Money** — measure (never assume) which wallets have
      predictive value and which consistently lose.
    * **Behaviour / Influence** — classify how a wallet trades and how much its
      opinion should weigh.
    * **Scoring / Explainability** — a final, fully-explained Wallet Score.
    * **Knowledge Base / Timeline** — append-only history and versions.

It emits events and read models for the (later) AI Committee. It **never** makes
a trading decision, enables live trading, or runs any ML. It only *knows*.
"""

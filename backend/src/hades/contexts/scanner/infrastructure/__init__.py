"""Scanner infrastructure — concrete adapters for the Scanner's domain ports.

Each DEX/aggregator is an independent :class:`TokenSource` adapter (no shared
business logic between them, only a common HTTP-polling base). Metadata providers
adapt on-chain RPC and off-chain aggregators to :class:`MetadataProvider`. The
seen-token registry and discovery repository adapt Redis and PostgreSQL.
"""

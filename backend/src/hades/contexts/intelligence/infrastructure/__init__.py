"""Wallet Intelligence infrastructure — I/O adapters (Postgres, on-chain reads).

All side effects live here so the domain and application layers stay pure. Every
adapter ships in two flavours: a PostgreSQL implementation for the running system
and an in-memory one for fast, deterministic tests.
"""

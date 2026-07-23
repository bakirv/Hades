"""Notification context — outward alerts (Discord-first, extensible).

Responsibility:
    * Subscribe to noteworthy events (trade approved/filled, position closed,
      kill switch, health degraded) and deliver human-readable alerts.
    * Respect a minimum severity threshold and rate limits.
    * Be transport-agnostic behind a :class:`Notifier` port; Discord is the first
      adapter, Telegram/email/webhooks can follow without touching callers.

Phase 1 scope: contracts only.
"""

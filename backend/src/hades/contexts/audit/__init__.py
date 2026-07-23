"""Audit context — the platform's append-only trail of consequential actions.

Everything that changes the platform's behaviour or posture leaves a
``who / what / when / before / after`` record: model & strategy promotions,
weight and parameter changes, kill-switch / circuit-breaker / emergency
transitions, configuration edits and trading-mode switches. The trail is
append-only and never deleted — it is the auditable memory of the system.

The context is deliberately *cross-cutting but decoupled*: it never calls another
context. It records what other contexts already publish on the event bus (via
:class:`~hades.contexts.audit.application.subscriber.AuditSubscriber`) and offers
a small :class:`~hades.contexts.audit.domain.ports.AuditTrail` port that
platform services (e.g. the Configuration Manager) call directly.
"""

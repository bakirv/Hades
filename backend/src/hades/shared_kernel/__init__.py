"""Shared Kernel — cross-cutting building blocks shared by every bounded context.

Nothing here knows about a *specific* domain (scanning, scoring, execution…).
It provides the primitives every context builds on: configuration, structured
logging, observability, the DDD tactical base classes, the event-sourcing and
CQRS infrastructure, persistence and the common error hierarchy.

Dependency rule: contexts may import from ``shared_kernel``; ``shared_kernel``
must NEVER import from a context.
"""

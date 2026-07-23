"""Bounded contexts — the vertical slices of Hades' domain.

Each sub-package is an independent module with its own ``domain`` (entities,
value objects, events, ports), ``application`` (use cases / command + query
handlers) and ``infrastructure`` (adapters implementing the ports). Contexts
communicate **only** through domain events on the bus and through the shared
published language in :mod:`hades.contexts.common`. No context imports another
context's ``application`` or ``infrastructure`` — this is what keeps them
independently deployable.

Pipeline (all via events, never direct calls):

    scanner → features → security → wallet → market → scoring
            → risk → execution → portfolio → learning
    (research, notification, monitoring observe the whole flow)
"""

"""Hades — professional quantitative platform for Solana meme coins.

The package is organised as a *modular monolith* built on Clean Architecture,
Domain-Driven Design, Event Sourcing and CQRS. Each bounded context under
``hades.contexts`` is independently deployable in the future; today they run in
one process wired together at ``hades.bootstrap``.
"""

__version__ = "0.3.0"

"""Hades — professional quantitative platform for Solana meme coins.

The package is organised as a *modular monolith* built on Clean Architecture,
Domain-Driven Design, Event Sourcing and CQRS. Each bounded context under
``hades.contexts`` is independently deployable in the future; today they run in
one process wired together at ``hades.bootstrap``.
"""

# Single source of truth for the platform version. ``pyproject.toml`` derives its
# ``version`` from this attribute (``[tool.setuptools.dynamic]``), so the packaged
# metadata, the runtime the API exposes (``/api/v1/status``, ``/version``, the WS
# handshake, OpenAPI) and the docs can never drift apart again. Bump it here only.
__version__ = "0.10.0"

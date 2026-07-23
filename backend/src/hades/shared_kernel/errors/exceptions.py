"""Typed exception hierarchy.

Layers raise the most specific error; the API layer maps them to HTTP codes in
one place. Distinguishing *domain* errors (a business rule was violated) from
*infrastructure* errors (a database was unreachable) is what lets the platform
retry the latter and reject the former.
"""

from __future__ import annotations

from typing import Any


class HadesError(Exception):
    """Root of every error raised inside Hades."""

    def __init__(self, message: str, *, context: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.context = context or {}


# --- domain-layer errors (business rules) ------------------------------------
class DomainError(HadesError):
    """A domain invariant or business rule was violated."""


class ValidationError(DomainError):
    """Input failed validation before a command could be accepted."""


class NotFoundError(DomainError):
    """A referenced aggregate or entity does not exist."""


class ConcurrencyError(DomainError):
    """Optimistic-concurrency clash writing to the event store."""


class PermissionDeniedError(DomainError):
    """An action was blocked by a policy (e.g. live-trading safety gate)."""


# --- infrastructure-layer errors (transient / external) ----------------------
class InfrastructureError(HadesError):
    """A downstream dependency failed (db, cache, RPC, external API)."""


class ConfigurationError(HadesError):
    """The platform is mis-configured and cannot start or operate safely."""

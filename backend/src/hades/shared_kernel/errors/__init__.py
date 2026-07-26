"""Common error hierarchy shared by all contexts."""

from hades.shared_kernel.errors.describe import describe_exception
from hades.shared_kernel.errors.exceptions import (
    ConcurrencyError,
    ConfigurationError,
    DomainError,
    HadesError,
    InfrastructureError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)

__all__ = [
    "ConcurrencyError",
    "ConfigurationError",
    "DomainError",
    "HadesError",
    "InfrastructureError",
    "NotFoundError",
    "PermissionDeniedError",
    "ValidationError",
    "describe_exception",
]

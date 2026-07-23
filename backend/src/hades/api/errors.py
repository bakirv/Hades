"""Single place that maps the domain error hierarchy to HTTP responses.

Routers never build error responses by hand; they raise domain errors and these
handlers translate them consistently.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from hades.shared_kernel.errors import (
    ConcurrencyError,
    ConfigurationError,
    DomainError,
    HadesError,
    InfrastructureError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)

_STATUS_MAP: list[tuple[type[HadesError], int]] = [
    (ValidationError, 422),
    (NotFoundError, 404),
    (PermissionDeniedError, 403),
    (ConcurrencyError, 409),
    (ConfigurationError, 500),
    (InfrastructureError, 503),
    (DomainError, 400),
]


def _status_for(exc: HadesError) -> int:
    for err_type, status in _STATUS_MAP:
        if isinstance(exc, err_type):
            return status
    return 500


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HadesError)
    async def _handle(_: Request, exc: HadesError) -> JSONResponse:
        return JSONResponse(
            status_code=_status_for(exc),
            content={
                "error": type(exc).__name__,
                "message": exc.message,
                "context": exc.context,
            },
        )

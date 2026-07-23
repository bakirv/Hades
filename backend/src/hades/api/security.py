"""Authentication scaffolding (prepared, disabled by default).

Phase 2 ships the *seam* for authentication without enforcing it: when
``API_AUTH_ENABLED`` is false (the default) every request is allowed and attributed
to the ``system`` principal. When enabled, a static API key in the
``X-API-Key`` header is required. A later phase can replace this with real
sessions/JWT without touching the routers, which only depend on
:func:`get_principal`.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass

from fastapi import Depends, Header, Request

from hades.bootstrap import Container
from hades.shared_kernel.errors import PermissionDeniedError


@dataclass(frozen=True)
class Principal:
    """The authenticated caller (or the implicit ``system`` when auth is off)."""

    identity: str
    authenticated: bool


def _container(request: Request) -> Container:
    return request.app.state.container  # type: ignore[no-any-return]


def get_principal(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    container: Container = Depends(_container),
) -> Principal:
    api = container.settings.api
    if not api.auth_enabled:
        return Principal(identity="system", authenticated=False)
    # Constant-time comparison — never leak key length/prefix via timing.
    if x_api_key and api.auth_api_key and hmac.compare_digest(x_api_key, api.auth_api_key):
        return Principal(identity="operator", authenticated=True)
    raise PermissionDeniedError("invalid or missing API key")

"""FastAPI application factory.

Builds the :class:`Container` on startup, stores it on ``app.state`` for the
dependency helpers, wires routers and cross-cutting middleware, and disposes
resources on shutdown. Nothing here knows domain logic — routers delegate to the
command/query buses.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from hades import __version__
from hades.api.errors import register_exception_handlers
from hades.api.routers import (
    audit,
    committee,
    config,
    execution,
    health,
    info,
    intelligence,
    meta,
    metrics,
    portfolio,
    research,
    risk,
    scanner,
    security,
    status,
    strategy,
    trading,
    version,
)
from hades.api.ws import routes as ws_routes
from hades.bootstrap import build_container
from hades.shared_kernel.config import get_settings
from hades.shared_kernel.logging import get_logger

_logger = get_logger("api")


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    container = build_container(settings, role="api")
    app.state.container = container
    app.state.started_at = time.time()
    _logger.info("api_started", env=settings.env)
    try:
        yield
    finally:
        await container.shutdown()
        _logger.info("api_stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Hades",
        version=__version__,
        description="Professional quantitative platform for Solana meme coins.",
        docs_url="/docs" if settings.api.enable_docs else None,
        redoc_url="/redoc" if settings.api.enable_docs else None,
        lifespan=_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(meta.router)
    app.include_router(metrics.router)
    app.include_router(version.router)
    app.include_router(info.router)
    app.include_router(status.router)
    app.include_router(config.router)
    app.include_router(trading.router)
    app.include_router(execution.router)
    app.include_router(scanner.router)
    app.include_router(security.router)
    app.include_router(intelligence.router)
    app.include_router(committee.router)
    app.include_router(strategy.router)
    app.include_router(portfolio.router)
    app.include_router(risk.router)
    app.include_router(research.router)
    app.include_router(audit.router)
    app.include_router(ws_routes.router)

    return app

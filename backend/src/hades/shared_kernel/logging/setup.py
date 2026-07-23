"""Centralised structlog configuration.

Every service configures logging once at startup via :func:`configure_logging`,
then obtains bound loggers via :func:`get_logger`. Output is:

- **stdout** — JSON in production (ships straight to a log pipeline / Docker),
  coloured console in development;
- **rotating files** — a combined ``hades.log`` plus one file per functional
  domain (engine, api, dashboard, research, trading, risk, discord, watchdog),
  each size-rotated;
- an **in-memory ring buffer** — the live feed behind the dashboard terminal.

structlog is routed through the stdlib logging machinery so third-party loggers
(uvicorn, sqlalchemy) share the exact same handlers and formatting.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Mapping
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import structlog

from hades.shared_kernel.logging.ring_buffer import get_log_buffer

_CONFIGURED = False

# logger-name prefix → domain log file. First match wins; everything also goes
# to the combined ``hades.log`` and to stdout.
_DOMAIN_PREFIXES: dict[str, tuple[str, ...]] = {
    "engine": ("engine",),
    "api": ("api",),
    "dashboard": ("dashboard",),
    "research": ("research",),
    "trading": ("execution", "portfolio", "trade", "market"),
    "risk": ("risk",),
    "discord": ("discord", "notification"),
    "watchdog": ("watchdog", "monitoring", "healthcheck"),
}


def _domain_for(name: str) -> str | None:
    for domain, prefixes in _DOMAIN_PREFIXES.items():
        if any(name == p or name.startswith(p + ".") for p in prefixes):
            return domain
    return None


class _DomainFilter(logging.Filter):
    """Passes only records whose logger name maps to ``domain``."""

    def __init__(self, domain: str) -> None:
        super().__init__()
        self._domain = domain

    def filter(self, record: logging.LogRecord) -> bool:
        return _domain_for(record.name) == self._domain


def _ring_buffer_processor(
    _logger: Any, _method: str, event_dict: Mapping[str, Any]
) -> Mapping[str, Any]:
    """structlog processor: mirror each record into the terminal ring buffer."""
    get_log_buffer().append(dict(event_dict))
    return event_dict


def configure_logging(
    *,
    level: str = "INFO",
    fmt: str = "json",
    to_file: bool = False,
    directory: str = "/var/log/hades",
    rotation_max_bytes: int = 50_000_000,
    rotation_backups: int = 10,
    ring_buffer_size: int = 2000,
) -> None:
    """Configure structlog + stdlib logging. Idempotent."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    get_log_buffer(maxlen=ring_buffer_size)
    log_level = getattr(logging, level.upper(), logging.INFO)

    pre_chain: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=[
            *pre_chain,
            _ring_buffer_processor,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        cache_logger_on_first_use=True,
    )

    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer()
        if fmt == "json"
        else structlog.dev.ConsoleRenderer(colors=True)
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=pre_chain,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(log_level)

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    root.addHandler(stdout_handler)

    if to_file:
        _attach_file_handlers(root, formatter, directory, rotation_max_bytes, rotation_backups)

    _CONFIGURED = True


def _attach_file_handlers(
    root: logging.Logger,
    formatter: logging.Formatter,
    directory: str,
    max_bytes: int,
    backups: int,
) -> None:
    """Add the combined + per-domain rotating file handlers (best effort)."""
    try:
        log_dir = Path(directory)
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Filesystem not writable (e.g. dev host without the volume) — stdout is
        # still active, so logging keeps working; just skip file sinks.
        return

    combined = RotatingFileHandler(
        log_dir / "hades.log", maxBytes=max_bytes, backupCount=backups, encoding="utf-8"
    )
    combined.setFormatter(formatter)
    root.addHandler(combined)

    for domain in _DOMAIN_PREFIXES:
        handler = RotatingFileHandler(
            log_dir / f"{domain}.log",
            maxBytes=max_bytes,
            backupCount=backups,
            encoding="utf-8",
        )
        handler.setFormatter(formatter)
        handler.addFilter(_DomainFilter(domain))
        root.addHandler(handler)


def get_logger(name: str | None = None, **initial_context: Any) -> structlog.stdlib.BoundLogger:
    """Return a bound logger, optionally pre-bound with context key/values."""
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    if initial_context:
        logger = logger.bind(**initial_context)
    return logger

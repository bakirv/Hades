"""Execution Engine runtime composition — wires and runs the executor.

Process-level wiring (the ops layer may import application + infrastructure). It
assembles the Execution Engine from the container and subscribes it to the end of
the decision pipeline:

    risk ─TradeApproved─► [Execution Engine → paper|live executor]
        ─► OrderFilled/OrderFailed
        ─► PositionOpened/PositionClosed ─► [Portfolio Manager]

The engine is the only component that knows the mode; the runtime feeds it a mode
provider backed by the guarded :class:`TradingModeService` (DB authority ANDed
with the hard env gate). The **live executor is only built when the live gate is
on and its adapters (signer/quote/RPC) are supplied** — otherwise the engine has
paper only and can never route real orders. Status snapshots are published to
Redis for the dashboard, exactly like the Risk runtime.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from hades.bootstrap import Container
from hades.contexts.execution.application.factory import (
    ExecutionEngineBundle,
    build_execution_engine,
)
from hades.contexts.execution.application.metrics import ExecutionMetrics
from hades.contexts.execution.application.trading_mode import TradingModeService
from hades.contexts.execution.application.wallet_manager import WalletManager
from hades.contexts.execution.infrastructure.trading_mode_repository import TradingModeRepository
from hades.contexts.risk.domain.events import TradeApproved
from hades.shared_kernel.cache import CacheService
from hades.shared_kernel.domain.events import DomainEvent
from hades.shared_kernel.logging import get_logger

_logger = get_logger("execution.runtime")

#: Redis namespace/key the runtime publishes execution status under.
EXECUTION_STATUS_NAMESPACE = "execution"
STATUS_KEY = "status"
_STATUS_TTL_SECONDS = 30


class ExecutionRuntime:
    """Owns the wired Execution Engine and its lifecycle."""

    def __init__(self, container: Container) -> None:
        self._c = container
        self._stop = asyncio.Event()
        self._metrics = ExecutionMetrics(container.metrics)
        self._cache = CacheService(container.redis, namespace=EXECUTION_STATUS_NAMESPACE)

        repo = (
            TradingModeRepository(container.database)
            if container.database is not None
            else None
        )
        self._mode_service = TradingModeService(
            container.settings,
            event_bus=container.event_bus,
            notifier=container.notification,
            repository=repo,
        )
        self._wallet = WalletManager(container.settings.wallet)

        self._bundle: ExecutionEngineBundle = build_execution_engine(
            container.settings,
            event_bus=container.event_bus,
            notifier=container.notification,
            mode_provider=self._resolve_mode,
            metrics=self._metrics,
            # Live adapters (signer/quote/rpc) are supplied in a later phase; until
            # then the engine is paper-only regardless of the gate — fail-safe.
        )
        self._register()

    async def _resolve_mode(self) -> str:
        status = await self._mode_service.current()
        return status.mode

    def _register(self) -> None:
        self._c.event_bus.subscribe(TradeApproved.__name__, self._on_trade_approved)

    async def _on_trade_approved(self, event: DomainEvent) -> None:
        if not isinstance(event, TradeApproved):
            return
        try:
            await self._bundle.engine.on_trade_approved(event)
        except Exception as exc:  # one bad approval must not kill the runtime
            _logger.error("execution_failed", mint=str(event.token.mint), error=str(exc))

    # -- lifecycle ------------------------------------------------------------

    async def start(self) -> list[asyncio.Task[None]]:
        tasks = [asyncio.create_task(self._publish_status_loop(), name="execution-status")]
        _logger.info(
            "execution_runtime_started",
            enabled=self._c.settings.execution.enabled,
            live_executor=self._bundle.live_enabled,
        )
        return tasks

    async def stop(self) -> None:
        self._stop.set()
        _logger.info("execution_runtime_stopped")

    # -- dashboard status -----------------------------------------------------

    async def _snapshot(self) -> dict[str, Any]:
        mode = await self._mode_service.current()
        wallet = await self._wallet.health()
        return {
            "enabled": self._c.settings.execution.enabled,
            "mode": mode.mode,
            "is_live": mode.is_live,
            "live_gate_enabled": mode.live_gate_enabled,
            "live_executor_available": self._bundle.live_enabled,
            "orders": self._bundle.order_manager.counts(),
            "recent_orders": self._bundle.order_manager.recent(limit=20),
            "recent_transactions": self._bundle.transaction_manager.recent(limit=20),
            "transaction_stats": self._bundle.transaction_manager.stats(),
            "wallet": {
                "configured": wallet.configured,
                "public_key": wallet.public_key,
                "balance_sol": wallet.balance_sol,
                "healthy": wallet.healthy,
                "detail": wallet.detail,
            },
            "updated_at": time.time(),
        }

    async def _publish_status_loop(self) -> None:
        interval = self._c.settings.execution.status_interval_seconds
        while not self._stop.is_set():
            try:
                snapshot = await self._snapshot()
                await self._cache.set(STATUS_KEY, snapshot, ttl_seconds=_STATUS_TTL_SECONDS)
            except Exception as exc:  # status publishing is best-effort
                _logger.warning("execution_status_publish_failed", error=str(exc))
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except TimeoutError:
                continue

    # -- accessors for the API ------------------------------------------------

    @property
    def bundle(self) -> ExecutionEngineBundle:
        return self._bundle

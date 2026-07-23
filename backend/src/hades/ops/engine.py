"""Decision Engine process — the future home of the trading decision loop.

In later phases the Engine hosts the pipeline that turns discovered tokens into
scored signals and (via the Risk Manager) into orders. Phase 2 ships only the
supervised skeleton: it comes up on the event bus, heartbeats, and idles. It
contains **no** scanner, strategy or AI logic — that is deliberately out of scope
for the infrastructure phase.
"""

from __future__ import annotations

from hades.ops.service import ServiceProcess


class Engine(ServiceProcess):
    """The decision-engine process (skeleton only in Phase 2)."""

    role = "engine"

    async def setup(self) -> None:
        self._log.info(
            "engine_ready",
            trading_mode=self._container.settings.trading_mode,
            is_live=self._container.settings.is_live,
            note="no strategies/scanner/AI in Phase 2",
        )

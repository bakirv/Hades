"""WebSocket connection manager — topic-based fan-out.

Tracks connected clients per topic and broadcasts messages to them. Broadcasts
are best-effort: a send failure just drops that connection (it will reconnect).
Used to push events/notifications/state to the dashboard terminal in real time.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket

from hades.shared_kernel.logging import get_logger

_logger = get_logger("dashboard")


class ConnectionManager:
    """Fan-out registry of WebSocket connections grouped by topic."""

    def __init__(self) -> None:
        self._topics: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, topic: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._topics.setdefault(topic, set()).add(websocket)
        _logger.debug("ws_connected", topic=topic)

    async def disconnect(self, topic: str, websocket: WebSocket) -> None:
        async with self._lock:
            self._topics.get(topic, set()).discard(websocket)
        _logger.debug("ws_disconnected", topic=topic)

    async def broadcast(self, topic: str, message: Any) -> None:
        async with self._lock:
            targets = list(self._topics.get(topic, set()))
        dead: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_json(message)
            except Exception:  # drop broken sockets silently
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._topics.get(topic, set()).discard(ws)


_manager: ConnectionManager | None = None


def get_connection_manager() -> ConnectionManager:
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager

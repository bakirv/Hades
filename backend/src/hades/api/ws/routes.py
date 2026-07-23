"""WebSocket endpoints for the dashboard.

- ``/ws/terminal`` — the real-time terminal: sends a snapshot of recent log lines
  then streams new ones as they are produced (server tails the ring buffer and
  pushes; the client never polls).
- ``/ws/status``   — streams runtime posture (mode, is_live, uptime) on an interval.

Both are push channels, satisfying the "no unnecessary polling" rule.
"""

from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from hades import __version__
from hades.bootstrap import Container
from hades.shared_kernel.logging import get_log_buffer

router = APIRouter(tags=["websocket"])

_TERMINAL_POLL_SECONDS = 0.5


@router.websocket("/ws/terminal")
async def terminal(websocket: WebSocket) -> None:
    await websocket.accept()
    buffer = get_log_buffer()
    last_seq, recent = buffer.recent(limit=200)
    await websocket.send_json({"type": "snapshot", "records": recent})
    try:
        while True:
            await asyncio.sleep(_TERMINAL_POLL_SECONDS)
            last_seq, new_records = buffer.read_since(last_seq)
            if new_records:
                await websocket.send_json({"type": "append", "records": new_records})
    except WebSocketDisconnect:
        return


@router.websocket("/ws/status")
async def status_stream(websocket: WebSocket) -> None:
    container: Container = websocket.app.state.container
    started_at = getattr(websocket.app.state, "started_at", time.time())
    interval = max(1.0, container.settings.dashboard.refresh_interval_ms / 1000.0)
    await websocket.accept()
    try:
        while True:
            s = container.settings
            await websocket.send_json(
                {
                    "type": "status",
                    "version": __version__,
                    "environment": s.env,
                    "trading_mode": s.trading_mode,
                    "is_live": s.is_live,
                    "event_bus_transport": s.event_bus.transport,
                    "uptime_seconds": round(time.time() - started_at, 1),
                }
            )
            await asyncio.sleep(interval)
    except WebSocketDisconnect:
        return

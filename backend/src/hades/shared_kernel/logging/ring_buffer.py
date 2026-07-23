"""In-memory ring buffer of recent log records.

Feeds the real-time terminal in the dashboard: the WebSocket endpoint tails this
buffer and pushes new lines to connected clients (no page refresh, no client
polling). It holds only the most recent N records — it is a live view, never a
store (that role belongs to the rotating log files and the event store).
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Any


class LogRingBuffer:
    """Thread-safe, bounded buffer of structured log records with sequence ids."""

    def __init__(self, maxlen: int = 2000) -> None:
        self._buffer: deque[tuple[int, dict[str, Any]]] = deque(maxlen=maxlen)
        self._seq = 0
        self._lock = threading.Lock()

    def append(self, record: dict[str, Any]) -> None:
        with self._lock:
            self._seq += 1
            self._buffer.append((self._seq, dict(record)))

    def read_since(self, after_seq: int) -> tuple[int, list[dict[str, Any]]]:
        """Return (latest_seq, records with seq > after_seq)."""
        with self._lock:
            records = [rec for seq, rec in self._buffer if seq > after_seq]
            latest = self._seq
        return latest, records

    def recent(self, limit: int = 200) -> tuple[int, list[dict[str, Any]]]:
        with self._lock:
            items = list(self._buffer)[-limit:]
            latest = self._seq
        return latest, [rec for _seq, rec in items]


# Process-wide singleton the logging processor writes into and the WS reads from.
_ring_buffer: LogRingBuffer | None = None


def get_log_buffer(maxlen: int = 2000) -> LogRingBuffer:
    global _ring_buffer
    if _ring_buffer is None:
        _ring_buffer = LogRingBuffer(maxlen=maxlen)
    return _ring_buffer

"""WebSocket presentation layer.

All live dashboard data travels over WebSocket (push, never client polling): the
real-time terminal tails the log ring buffer, and the status channel streams
runtime posture. A :class:`ConnectionManager` fans out messages to subscribers.
"""

from hades.api.ws.manager import ConnectionManager, get_connection_manager

__all__ = ["ConnectionManager", "get_connection_manager"]

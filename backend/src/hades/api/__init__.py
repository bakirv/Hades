"""Presentation layer — the REST API + WebSocket surface.

This layer is a thin adapter: it translates HTTP/WS into commands and queries on
the buses and maps domain errors to status codes. It contains no business logic.
"""

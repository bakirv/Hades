"""Ports defined by the Notification context."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol, runtime_checkable

from hades.shared_kernel.domain.base import ValueObject


class Severity(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class Notification(ValueObject):
    """A transport-agnostic message ready to be delivered."""

    title: str
    body: str
    severity: Severity
    tags: dict[str, str] = {}


@runtime_checkable
class Notifier(Protocol):
    """Delivers a notification over one channel (Discord, Telegram, email…)."""

    @property
    def channel(self) -> str: ...

    async def send(self, notification: Notification) -> None: ...

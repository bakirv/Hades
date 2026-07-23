"""Auto-recovery heals what it can and escalates to Emergency Mode otherwise."""

from __future__ import annotations

from hades.contexts.monitoring.application.recovery import (
    EmergencyMode,
    RecoveryOrchestrator,
)
from hades.contexts.monitoring.infrastructure.recovery_actions import InMemoryEmergencyFlagStore
from hades.contexts.notification.application.publisher import NotificationPublisher
from hades.contexts.risk.domain.events import ACTION_ENTER_EMERGENCY, RiskControlCommandIssued
from hades.shared_kernel.domain.events import DomainEvent
from hades.shared_kernel.events import InMemoryEventBus


class _Action:
    def __init__(self, name: str, component: str, result: bool, *, raises: bool = False) -> None:
        self._name = name
        self._component = component
        self._result = result
        self._raises = raises

    @property
    def name(self) -> str:
        return self._name

    def handles(self, component: str) -> bool:
        return self._component in component

    async def attempt(self) -> bool:
        if self._raises:
            raise RuntimeError("boom")
        return self._result


def _emergency() -> tuple[EmergencyMode, InMemoryEmergencyFlagStore, list[DomainEvent]]:
    bus = InMemoryEventBus()
    captured: list[DomainEvent] = []
    bus.subscribe(RiskControlCommandIssued.__name__, lambda e: _collect(captured, e))
    flags = InMemoryEmergencyFlagStore()
    emergency = EmergencyMode(event_bus=bus, notifier=NotificationPublisher(bus), flags=flags)
    return emergency, flags, captured


async def _collect(sink: list[DomainEvent], event: DomainEvent) -> None:
    sink.append(event)


async def test_emergency_activate_publishes_command_and_is_idempotent() -> None:
    emergency, flags, captured = _emergency()

    assert await emergency.activate("catastrophe") is True
    assert await flags.is_active() is True
    assert len(captured) == 1
    assert isinstance(captured[0], RiskControlCommandIssued)
    assert captured[0].action == ACTION_ENTER_EMERGENCY

    # Already active → no-op, no second command.
    assert await emergency.activate("again") is False
    assert len(captured) == 1


async def test_orchestrator_recovers_via_first_working_action() -> None:
    emergency, flags, _ = _emergency()
    orch = RecoveryOrchestrator(
        [_Action("bad", "redis", False), _Action("good", "redis", True)],
        emergency=emergency,
        notifier=NotificationPublisher(InMemoryEventBus()),
        max_attempts=3,
    )
    assert await orch.recover("redis", "no reply") is True
    assert await flags.is_active() is False


async def test_orchestrator_escalates_after_max_attempts() -> None:
    emergency, flags, _ = _emergency()
    orch = RecoveryOrchestrator(
        [_Action("always_fails", "postgres", False)],
        emergency=emergency,
        notifier=NotificationPublisher(InMemoryEventBus()),
        max_attempts=2,
    )
    assert await orch.recover("postgres", "down") is False
    assert await flags.is_active() is False  # not yet — one attempt left
    assert await orch.recover("postgres", "down") is False
    assert await flags.is_active() is True  # exhausted → Emergency Mode


async def test_raising_action_counts_as_failure() -> None:
    emergency, _, _ = _emergency()
    orch = RecoveryOrchestrator(
        [_Action("explodes", "rpc", True, raises=True)],
        emergency=emergency,
        notifier=NotificationPublisher(InMemoryEventBus()),
        max_attempts=5,
    )
    assert await orch.recover("rpc", "") is False

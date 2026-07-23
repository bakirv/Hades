"""The Production Checklist gates LIVE on every required subsystem."""

from __future__ import annotations

from hades.contexts.monitoring.application.production_checklist import ProductionChecklist
from hades.contexts.monitoring.domain.models import ComponentHealth, HealthStatus
from hades.contexts.monitoring.infrastructure.recovery_actions import InMemoryEmergencyFlagStore
from hades.shared_kernel.config import get_settings


class _FakeProbe:
    def __init__(self, name: str, status: HealthStatus) -> None:
        self._name = name
        self._status = status

    @property
    def name(self) -> str:
        return self._name

    async def check(self) -> ComponentHealth:
        return ComponentHealth(name=self._name, status=self._status, detail="fake")


def _healthy_probes() -> list[_FakeProbe]:
    return [
        _FakeProbe("postgres", HealthStatus.HEALTHY),
        _FakeProbe("redis", HealthStatus.HEALTHY),
        _FakeProbe("rpc", HealthStatus.HEALTHY),
    ]


def _checklist(probes: list[_FakeProbe], flags: InMemoryEmergencyFlagStore) -> ProductionChecklist:
    return ProductionChecklist(get_settings(), probes=probes, emergency=flags)  # type: ignore[arg-type]


async def test_infra_failure_blocks_live() -> None:
    probes = [
        _FakeProbe("postgres", HealthStatus.UNHEALTHY),
        _FakeProbe("redis", HealthStatus.HEALTHY),
    ]
    report = await _checklist(probes, InMemoryEmergencyFlagStore()).report()
    assert report["ready"] is False
    assert "postgres" in report["required_failed"]


async def test_active_emergency_blocks_live() -> None:
    flags = InMemoryEmergencyFlagStore()
    await flags.set_active(True, reason="test", actor="tester")
    report = await _checklist(_healthy_probes(), flags).report()
    assert "emergency_mode_inactive" in report["required_failed"]
    assert report["ready"] is False


async def test_readiness_tuples_carry_required_flag() -> None:
    tuples = await _checklist(_healthy_probes(), InMemoryEmergencyFlagStore()).readiness()
    # Every tuple is (name, ok, detail, required); wallet is required and, by
    # default (no wallet configured), failing — so LIVE stays blocked.
    wallet = next(t for t in tuples if t[0] == "wallet")
    assert wallet[3] is True  # required
    assert wallet[1] is False  # not configured by default

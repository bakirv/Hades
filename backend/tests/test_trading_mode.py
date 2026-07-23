"""The paper/live switch enforces its safety protocol."""

from __future__ import annotations

import pytest

from hades.contexts.execution.application.trading_mode import (
    ReadinessCheck,
    ReadinessReport,
    TradingModeService,
)
from hades.contexts.notification.application.publisher import NotificationPublisher
from hades.shared_kernel.config import get_settings
from hades.shared_kernel.config.settings import TradingMode
from hades.shared_kernel.errors import ValidationError
from hades.shared_kernel.events import InMemoryEventBus


def _service() -> TradingModeService:
    bus = InMemoryEventBus()
    return TradingModeService(
        get_settings(),
        event_bus=bus,
        notifier=NotificationPublisher(bus),
        repository=None,
    )


async def test_default_mode_is_paper_and_not_live() -> None:
    status = await _service().current()
    assert status.mode == "paper"
    assert status.is_live is False


async def test_enabling_live_requires_explicit_confirmation() -> None:
    with pytest.raises(ValidationError):
        await _service().request_switch(TradingMode.LIVE, actor="tester", confirm=False)


async def test_switch_to_same_mode_is_noop() -> None:
    status = await _service().request_switch(TradingMode.PAPER, actor="tester", confirm=True)
    assert status.mode == "paper"
    assert status.is_live is False


def test_readiness_report_requires_all_required_checks() -> None:
    report = ReadinessReport(
        checks=[
            ReadinessCheck(name="a", ok=True, detail="", required=True),
            ReadinessCheck(name="b", ok=False, detail="", required=False),
        ]
    )
    assert report.ready is True

    report_bad = ReadinessReport(
        checks=[ReadinessCheck(name="a", ok=False, detail="", required=True)]
    )
    assert report_bad.ready is False

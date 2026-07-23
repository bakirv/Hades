"""The Position aggregate enforces its state machine and records events."""

from __future__ import annotations

from decimal import Decimal

import pytest

from hades.contexts.common.domain.value_objects import Money, TokenMint, TokenRef
from hades.contexts.portfolio.domain.events import PositionClosed, PositionOpened
from hades.contexts.portfolio.domain.models import Position, PositionStatus
from hades.shared_kernel.errors import DomainError

_MINT = "So11111111111111111111111111111111111111112"


def _new_position() -> Position:
    return Position(token=TokenRef(mint=TokenMint(address=_MINT)))


def test_open_records_event_and_advances_version() -> None:
    pos = _new_position()
    pos.open(entry_price=Money(amount="1"), quantity=Decimal(100), notional=Money(amount="100"))

    assert pos.status is PositionStatus.OPEN
    assert pos.version == 1
    events = pos.pull_events()
    assert isinstance(events[0], PositionOpened)
    assert not pos.has_pending_events  # pull clears the buffer


def test_cannot_open_twice() -> None:
    pos = _new_position()
    pos.open(entry_price=Money(amount="1"), quantity=Decimal(100), notional=Money(amount="100"))
    with pytest.raises(DomainError, match="already opened"):
        pos.open(entry_price=Money(amount="1"), quantity=Decimal(1), notional=Money(amount="1"))


def test_close_requires_open() -> None:
    pos = _new_position()
    with pytest.raises(DomainError, match="not open"):
        pos.close(exit_price=Money(amount="1"), realized_pnl=Money(amount="0"), reason="manual")


def test_full_lifecycle() -> None:
    pos = _new_position()
    pos.open(entry_price=Money(amount="1"), quantity=Decimal(100), notional=Money(amount="100"))
    pos.close(exit_price=Money(amount="2"), realized_pnl=Money(amount="100"), reason="take_profit")

    assert pos.status is PositionStatus.CLOSED
    events = pos.pull_events()
    assert isinstance(events[-1], PositionClosed)

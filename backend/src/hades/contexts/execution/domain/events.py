"""Domain events emitted by the Execution Engine."""

from __future__ import annotations

from hades.contexts.execution.domain.models import FillReport, OrderRequest
from hades.shared_kernel.domain.events import DomainEvent


class OrderSubmitted(DomainEvent):
    """An order was submitted to the venue (or the paper simulator)."""

    aggregate_type: str = "order"
    request: OrderRequest
    mode: str  # "paper" | "live" — recorded for audit, never branched on upstream


class OrderFilled(DomainEvent):
    """An order filled. The Portfolio Manager reacts to open/close a position."""

    aggregate_type: str = "order"
    fill: FillReport


class OrderFailed(DomainEvent):
    """An order failed (reverted, timed out, rejected)."""

    aggregate_type: str = "order"
    request: OrderRequest
    reason: str


class TradingModeChanged(DomainEvent):
    """The platform's trading mode was changed (paper ↔ live).

    Emitted only after every readiness verification passed and the change was
    audited. Downstream (dashboard, notifications) reflect the new posture from
    this event so the mode is never inconsistent across surfaces.
    """

    aggregate_type: str = "platform"
    previous_mode: str
    new_mode: str
    is_live: bool
    actor: str

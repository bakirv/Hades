"""Trading-mode endpoints — the guarded paper↔live switch.

- ``GET  /api/v1/trading/mode``         — current effective mode + live gate.
- ``POST /api/v1/trading/mode/verify``  — run the live-readiness checks only.
- ``POST /api/v1/trading/mode``         — request a mode change (verified + audited).

The switch can never enable live implicitly: enabling live requires the hard env
gate, all readiness checks to pass, and an explicit ``confirm: true``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from hades.api.dependencies import get_trading_mode_service
from hades.api.security import Principal, get_principal
from hades.contexts.execution.application.trading_mode import TradingModeService
from hades.shared_kernel.config.settings import TradingMode

router = APIRouter(prefix="/api/v1/trading", tags=["trading"])


class ModeChangeRequest(BaseModel):
    mode: TradingMode
    confirm: bool = False


def _report_dict(service_report: object) -> dict[str, object]:
    checks = getattr(service_report, "checks", [])
    return {
        "ready": getattr(service_report, "ready", False),
        "checks": [
            {"name": c.name, "ok": c.ok, "detail": c.detail, "required": c.required} for c in checks
        ],
    }


@router.get("/mode", summary="Current effective trading mode")
async def get_mode(
    service: TradingModeService = Depends(get_trading_mode_service),
) -> dict[str, object]:
    status = await service.current()
    return {
        "mode": status.mode,
        "is_live": status.is_live,
        "live_gate_enabled": status.live_gate_enabled,
    }


@router.post("/mode/verify", summary="Run live-readiness verification only")
async def verify_mode(
    service: TradingModeService = Depends(get_trading_mode_service),
) -> dict[str, object]:
    report = await service.verify_live_readiness()
    return _report_dict(report)


@router.post("/mode", summary="Request a trading-mode change (verified + audited)")
async def change_mode(
    body: ModeChangeRequest,
    request: Request,
    service: TradingModeService = Depends(get_trading_mode_service),
    principal: Principal = Depends(get_principal),
) -> dict[str, object]:
    source_ip = request.client.host if request.client else None
    status = await service.request_switch(
        body.mode, actor=principal.identity, confirm=body.confirm, source_ip=source_ip
    )
    return {
        "mode": status.mode,
        "is_live": status.is_live,
        "live_gate_enabled": status.live_gate_enabled,
    }

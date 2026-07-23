"""Production Checklist — the pre-LIVE gate over the whole platform.

Before real capital can ever be at risk, every load-bearing subsystem must be in
order. This checklist aggregates that verdict from two sources:

- **Live connectivity**, by running the same health probes the Watchdog uses
  (Postgres, Redis, RPC, and optionally API/dashboard/ClickHouse).
- **Subsystem posture**, from configuration (Risk Manager, wallet, Security
  Engine, AI Committee, Execution Engine, Notifications, Scanner, Watchdog,
  Backups, Docs) — plus the hard rule that **Emergency Mode must be inactive**.

Each item is ``required`` or advisory. It implements
:class:`~hades.contexts.execution.domain.ports.ProductionChecklistPort` via
:meth:`readiness`, so the trading-mode switch folds these required checks into its
live-readiness gate: any required failure blocks the switch to LIVE. The checklist
never enables anything — it can only withhold approval.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hades.contexts.monitoring.application.recovery import EmergencyFlagStore
from hades.contexts.monitoring.domain.models import HealthStatus
from hades.contexts.monitoring.domain.ports import HealthProbe
from hades.shared_kernel.config import Settings
from hades.shared_kernel.logging import get_logger

_logger = get_logger("monitoring.checklist")

# Infra probes whose failure must block LIVE (others are reported but advisory).
_REQUIRED_INFRA = frozenset({"postgres", "redis", "rpc"})


@dataclass(frozen=True)
class ChecklistItem:
    name: str
    ok: bool
    detail: str
    required: bool = True


class ProductionChecklist:
    """Aggregates platform readiness and gates the switch to LIVE."""

    def __init__(
        self,
        settings: Settings,
        *,
        probes: list[HealthProbe],
        emergency: EmergencyFlagStore,
    ) -> None:
        self._settings = settings
        self._probes = probes
        self._emergency = emergency

    async def evaluate(self) -> list[ChecklistItem]:
        items: list[ChecklistItem] = []
        items.extend(await self._infra_items())
        items.append(await self._emergency_item())
        items.extend(self._subsystem_items())
        return items

    async def readiness(self) -> list[tuple[str, bool, str, bool]]:
        """Port implementation: primitive tuples for the trading-mode gate."""
        return [(i.name, i.ok, i.detail, i.required) for i in await self.evaluate()]

    async def report(self) -> dict[str, object]:
        items = await self.evaluate()
        required_failed = [i.name for i in items if i.required and not i.ok]
        return {
            "ready": not required_failed,
            "required_failed": required_failed,
            "items": [
                {"name": i.name, "ok": i.ok, "detail": i.detail, "required": i.required}
                for i in items
            ],
        }

    # -- item builders --------------------------------------------------------

    async def _infra_items(self) -> list[ChecklistItem]:
        items: list[ChecklistItem] = []
        for probe in self._probes:
            try:
                health = await probe.check()
                ok = health.status is HealthStatus.HEALTHY
                detail = health.detail
            except Exception as exc:  # a probe error is an unhealthy result
                ok, detail = False, str(exc)
            items.append(
                ChecklistItem(
                    name=probe.name,
                    ok=ok,
                    detail=detail,
                    required=probe.name in _REQUIRED_INFRA,
                )
            )
        return items

    async def _emergency_item(self) -> ChecklistItem:
        active = await self._emergency.is_active()
        return ChecklistItem(
            name="emergency_mode_inactive",
            ok=not active,
            detail="Emergency Mode is ACTIVE" if active else "inactive",
            required=True,
        )

    def _subsystem_items(self) -> list[ChecklistItem]:
        s = self._settings
        notify_ok = s.notification.discord_enabled and bool(s.notification.discord_webhook_url)
        return [
            ChecklistItem(
                "risk_manager",
                s.risk.enabled and s.risk.max_position_size_usd > 0,
                "risk limits configured",
                required=True,
            ),
            ChecklistItem("wallet", s.wallet.is_configured, "wallet public key set", required=True),
            ChecklistItem(
                "execution_engine", s.execution.enabled, "execution enabled", required=True
            ),
            ChecklistItem("security_engine", s.security.enabled, "security enabled", required=True),
            ChecklistItem("watchdog", s.watchdog.enabled, "watchdog enabled", required=True),
            ChecklistItem(
                "ai_committee",
                s.learning.enabled and s.learning.committee_enabled,
                "committee enabled",
                required=False,
            ),
            ChecklistItem("scanner", s.scanner.enabled, "scanner enabled", required=False),
            ChecklistItem("notifications", notify_ok, "discord configured", required=False),
            ChecklistItem("backups", s.backup.enabled, "backups enabled", required=False),
            ChecklistItem(
                "documentation",
                Path(s.paths.docs).exists(),
                f"docs at {s.paths.docs}",
                required=False,
            ),
        ]

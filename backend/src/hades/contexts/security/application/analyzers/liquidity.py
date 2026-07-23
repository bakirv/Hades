"""Liquidity Analyzer — is the liquidity real, and can it be pulled?

Two independent questions:

* **Depth** — is there enough liquidity to enter and exit without catastrophic
  slippage? Thin pools are trivially manipulated and impossible to exit.
* **Lock** — is the LP burned or locked? Unlocked LP is the textbook rug: the
  deployer removes it and the token goes to zero. We insist on a high provable
  burned/locked share; when we cannot determine it at all, that is doubt, not a
  pass.

The analyzer records the full liquidity picture (depth, burned %, locked %, lock
provider/expiry) for the audit log and dashboard.
"""

from __future__ import annotations

from hades.contexts.security.application.analyzers.base import (
    build_report,
    flag,
    positive,
)
from hades.contexts.security.domain.models import (
    AnalyzerReport,
    RiskSeverity,
    SecurityInputs,
)


class LiquidityAnalyzer:
    """Judges liquidity depth and LP lock/burn status."""

    def __init__(
        self,
        *,
        min_liquidity_usd: float = 5_000.0,
        thin_liquidity_usd: float = 15_000.0,
        min_secured_lp_pct: float = 80.0,
    ) -> None:
        self._min_liquidity = min_liquidity_usd
        self._thin_liquidity = thin_liquidity_usd
        self._min_secured = min_secured_lp_pct

    @property
    def name(self) -> str:
        return "liquidity"

    def analyze(self, inputs: SecurityInputs) -> AnalyzerReport:
        pool = inputs.pool
        if pool is None:
            return build_report(
                self.name,
                flags=[
                    flag(
                        "NO_LIQUIDITY_DATA",
                        RiskSeverity.HIGH,
                        "No liquidity pool information available.",
                    )
                ],
                insufficient_data=True,
            )

        flags = []
        positives = []
        liquidity = float(pool.liquidity_usd)
        secured = pool.secured_pct
        facts: dict[str, object] = {
            "liquidity_usd": liquidity,
            "dex": pool.dex,
            "lp_burned_pct": pool.lp_burned_pct,
            "lp_locked_pct": pool.lp_locked_pct,
            "lp_secured_pct": secured,
            "lock_provider": pool.lock_provider,
            "lock_until": pool.lock_until.isoformat() if pool.lock_until else None,
        }

        # -- depth --
        if liquidity < self._min_liquidity:
            flags.append(
                flag(
                    "INSUFFICIENT_LIQUIDITY",
                    RiskSeverity.CRITICAL,
                    f"Liquidity ${liquidity:,.0f} is below the ${self._min_liquidity:,.0f} "
                    "floor — un-exitable.",
                )
            )
        elif liquidity < self._thin_liquidity:
            flags.append(
                flag(
                    "THIN_LIQUIDITY",
                    RiskSeverity.MEDIUM,
                    f"Liquidity ${liquidity:,.0f} is thin — high slippage / manipulation risk.",
                )
            )
        else:
            positives.append(
                positive("HEALTHY_LIQUIDITY", f"Liquidity ${liquidity:,.0f} is adequate.")
            )

        # -- lock / burn --
        if secured is None:
            flags.append(
                flag(
                    "LP_LOCK_UNKNOWN",
                    RiskSeverity.HIGH,
                    "Could not determine whether LP is locked or burned — treated as unsecured.",
                )
            )
        elif secured < self._min_secured:
            severity = RiskSeverity.CRITICAL if secured < 50.0 else RiskSeverity.HIGH
            flags.append(
                flag(
                    "LP_NOT_SECURED",
                    severity,
                    f"Only {secured:.1f}% of LP is burned/locked (need "
                    f"{self._min_secured:.0f}%) — remainder is rug-pullable.",
                )
            )
        else:
            how = "burned" if (pool.lp_burned_pct or 0) >= (pool.lp_locked_pct or 0) else "locked"
            positives.append(positive("LP_SECURED", f"{secured:.1f}% of LP {how}."))

        return build_report(self.name, flags=flags, positives=positives, facts=facts)

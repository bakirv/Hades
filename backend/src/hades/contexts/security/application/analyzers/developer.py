"""Developer Analyzer — what is the deployer's track record?

Reputation is *earned over time*. Hades records every token a deployer ships and
how it ends (rug / survived / success); the assembler loads that accumulated
:class:`DeveloperReputation` here. A deployer with prior rugs is a strong flag; a
blacklisted (known-scammer) deployer is an outright veto. Crucially, an *unknown*
deployer is a mild penalty — never a free pass — because most rugs come from
fresh wallets with no history.

This cold-starts honestly: on day one every deployer is unknown, and the module
grows sharper as the platform observes more of the ecosystem. It never fabricates
a history it has not seen.
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


class DeveloperAnalyzer:
    """Judges the deployer's accumulated reputation."""

    def __init__(self, *, max_rug_rate: float = 0.25) -> None:
        self._max_rug_rate = max_rug_rate

    @property
    def name(self) -> str:
        return "developer"

    def analyze(self, inputs: SecurityInputs) -> AnalyzerReport:
        rep = inputs.developer
        if rep is None:
            return build_report(
                self.name,
                flags=[
                    flag(
                        "DEPLOYER_UNKNOWN",
                        RiskSeverity.LOW,
                        "Deployer could not be identified — no reputation available.",
                    )
                ],
                insufficient_data=True,
                base=100.0,
            )

        facts: dict[str, object] = {
            "deployer": rep.deployer,
            "tokens_created": rep.tokens_created,
            "rugs": rep.rugs,
            "survived": rep.survived,
            "successes": rep.successes,
            "rug_rate": rep.rug_rate,
            "is_known_scammer": rep.is_known_scammer,
            "avg_lifetime_hours": rep.avg_lifetime_hours,
        }
        flags = []
        positives = []

        if rep.is_known_scammer:
            flags.append(
                flag(
                    "KNOWN_SCAMMER",
                    RiskSeverity.CRITICAL,
                    f"Deployer {rep.deployer} is a known scammer (blacklisted).",
                )
            )
        elif not rep.is_known:
            # New deployer: mild penalty, flagged as insufficient data.
            return build_report(
                self.name,
                flags=[
                    flag(
                        "DEPLOYER_NO_HISTORY",
                        RiskSeverity.LOW,
                        "First time Hades has seen this deployer — no track record yet.",
                    )
                ],
                facts=facts,
                insufficient_data=True,
            )
        else:
            rug_rate = rep.rug_rate or 0.0
            if rep.rugs > 0 and rug_rate >= 0.5:
                flags.append(
                    flag(
                        "SERIAL_RUGGER",
                        RiskSeverity.CRITICAL,
                        f"Deployer has rugged {rep.rugs}/{rep.tokens_created} prior tokens.",
                    )
                )
            elif rep.rugs > 0 and rug_rate >= self._max_rug_rate:
                flags.append(
                    flag(
                        "DEPLOYER_PRIOR_RUGS",
                        RiskSeverity.HIGH,
                        f"Deployer has {rep.rugs} prior rug(s) (rate {rug_rate:.0%}).",
                    )
                )
            elif rep.rugs > 0:
                flags.append(
                    flag(
                        "DEPLOYER_SOME_RUGS",
                        RiskSeverity.MEDIUM,
                        f"Deployer has {rep.rugs} prior rug(s).",
                    )
                )

            if rep.successes >= 2 and rep.rugs == 0:
                positives.append(
                    positive(
                        "PROVEN_DEVELOPER",
                        f"Deployer has {rep.successes} prior successful token(s), no rugs.",
                    )
                )

        return build_report(self.name, flags=flags, positives=positives, facts=facts)

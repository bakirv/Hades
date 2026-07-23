"""Authority Analyzer — who still controls the token?

The single most important rug question: can the team still mint new supply or
freeze holders' wallets? A live **mint authority** means they can dilute you to
zero; a live **freeze authority** means they can lock your tokens so you can
never sell (a honeypot by another name). Both are treated as critical unless
renounced. Mutable metadata is a softer concern (rebrand / bait-and-switch).

Renounced authorities are surfaced as explicit positives — a legible approval is
as important as a legible rejection.
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


class AuthorityAnalyzer:
    """Judges mint / freeze / upgrade authorities and mutability."""

    @property
    def name(self) -> str:
        return "authority"

    def analyze(self, inputs: SecurityInputs) -> AnalyzerReport:
        mint = inputs.mint_account
        if mint is None:
            return build_report(
                self.name,
                flags=[
                    flag(
                        "AUTHORITY_UNKNOWN",
                        RiskSeverity.HIGH,
                        "Mint account unavailable — authority status unknown.",
                    )
                ],
                insufficient_data=True,
            )

        flags = []
        positives = []
        facts: dict[str, object] = {
            "mint_authority": mint.mint_authority,
            "freeze_authority": mint.freeze_authority,
            "mint_renounced": mint.mint_renounced,
            "freeze_renounced": mint.freeze_renounced,
        }

        if not mint.mint_renounced:
            flags.append(
                flag(
                    "MINT_AUTHORITY_ACTIVE",
                    RiskSeverity.CRITICAL,
                    f"Mint authority still active ({mint.mint_authority}) — supply can "
                    "be inflated at will.",
                )
            )
        else:
            positives.append(positive("MINT_RENOUNCED", "Mint authority renounced — fixed supply."))

        if not mint.freeze_renounced:
            flags.append(
                flag(
                    "FREEZE_AUTHORITY_ACTIVE",
                    RiskSeverity.CRITICAL,
                    f"Freeze authority still active ({mint.freeze_authority}) — holder "
                    "wallets can be frozen (un-sellable).",
                )
            )
        else:
            positives.append(
                positive(
                    "FREEZE_RENOUNCED", "Freeze authority renounced — wallets cannot be frozen."
                )
            )

        # Mutable metadata: softer risk (rebrand / impersonation after listing).
        # Only meaningful when we could read the stored flag.
        if inputs.is_mutable is not None:
            facts["is_mutable"] = inputs.is_mutable
            if inputs.is_mutable:
                flags.append(
                    flag(
                        "METADATA_MUTABLE",
                        RiskSeverity.MEDIUM,
                        "Token metadata is mutable — name/symbol/image can change post-launch.",
                    )
                )
            else:
                positives.append(positive("METADATA_IMMUTABLE", "Token metadata is immutable."))

        return build_report(self.name, flags=flags, positives=positives, facts=facts)

"""Contract Analyzer — is the token program itself safe?

Examines the mint account's owning program and any Token-2022 extensions. The
SPL Token program is the well-understood baseline; Token-2022 is legitimate but
its *extensions* (transfer fee, transfer hook, permanent delegate, default
account state) are the vehicle for the most sophisticated honeypots, so their
presence is a serious flag. An unknown owner program, or a mint that does not
exist / is uninitialised, is treated as maximally suspicious.

Detection only — this analyzer records everything and judges the *program*, not
the trade.
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
    TokenProgram,
)

# Canonical Solana token program ids.
SPL_TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"

# Token-2022 extensions that let the issuer change behaviour after launch. Their
# mere presence is a honeypot vector — we never assume they are benign.
_DANGEROUS_EXTENSIONS = frozenset(
    {
        "transfer_fee_config",
        "transfer_hook",
        "permanent_delegate",
        "default_account_state",
        "mint_close_authority",
        "confidential_transfer_mint",
    }
)


class ContractAnalyzer:
    """Judges the token's owning program and extensions."""

    @property
    def name(self) -> str:
        return "contract"

    def analyze(self, inputs: SecurityInputs) -> AnalyzerReport:
        mint = inputs.mint_account
        if mint is None:
            return build_report(
                self.name,
                flags=[
                    flag(
                        "MINT_ACCOUNT_UNREADABLE",
                        RiskSeverity.CRITICAL,
                        "Could not read the mint account on-chain — cannot verify the "
                        "token at all.",
                    )
                ],
                insufficient_data=True,
            )

        flags = []
        positives = []
        facts: dict[str, object] = {
            "owner_program": mint.owner_program,
            "program": mint.program.value,
            "decimals": mint.decimals,
            "supply": str(mint.supply),
            "extensions": list(mint.extensions),
        }

        if not mint.is_initialized:
            flags.append(
                flag(
                    "MINT_UNINITIALIZED",
                    RiskSeverity.CRITICAL,
                    "Mint account is not initialised.",
                )
            )

        if mint.program is TokenProgram.UNKNOWN and mint.owner_program not in {
            SPL_TOKEN_PROGRAM,
            TOKEN_2022_PROGRAM,
        }:
            flags.append(
                flag(
                    "UNKNOWN_TOKEN_PROGRAM",
                    RiskSeverity.CRITICAL,
                    f"Mint is owned by an unrecognised program {mint.owner_program!r}; "
                    "behaviour cannot be trusted.",
                )
            )
        elif mint.program is TokenProgram.TOKEN_2022:
            risky = sorted(set(mint.extensions) & _DANGEROUS_EXTENSIONS)
            if risky:
                flags.append(
                    flag(
                        "TOKEN2022_RISKY_EXTENSION",
                        RiskSeverity.CRITICAL,
                        "Token-2022 mint carries behaviour-changing extension(s): "
                        + ", ".join(risky),
                    )
                )
            else:
                flags.append(
                    flag(
                        "TOKEN2022_STANDARD",
                        RiskSeverity.LOW,
                        "Token-2022 program in use (no dangerous extensions found).",
                    )
                )
        else:
            positives.append(
                positive(
                    "STANDARD_SPL_TOKEN",
                    "Standard SPL Token program — well-understood behaviour.",
                )
            )

        if mint.decimals < 0 or mint.decimals > 18:
            flags.append(
                flag(
                    "ABNORMAL_DECIMALS",
                    RiskSeverity.MEDIUM,
                    f"Unusual decimals value ({mint.decimals}).",
                )
            )

        return build_report(self.name, flags=flags, positives=positives, facts=facts)

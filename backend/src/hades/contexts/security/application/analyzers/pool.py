"""Pool Analyzer — is the trading venue itself sound?

Where Liquidity judges *depth and lock*, this analyzer judges the *pool as a
venue*: does one exist at all, is it on a known DEX (Raydium / Orca / Meteora /
Pump.fun), is it dust-sized, or does it look abandoned (created but never
traded)? Fake or duplicate pools are a common bait — a healthy-looking token
whose only pool is a decoy.

With the pool data the Scanner currently surfaces this is a focused check; it
deepens automatically as more pool sources are wired in.
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

_KNOWN_DEXES = frozenset({"raydium", "orca", "meteora", "pumpfun", "jupiter"})
_DUST_LIQUIDITY_USD = 500.0


class PoolAnalyzer:
    """Judges the existence, provenance and health of the trading pool."""

    @property
    def name(self) -> str:
        return "pool"

    def analyze(self, inputs: SecurityInputs) -> AnalyzerReport:
        pool = inputs.pool
        if pool is None:
            return build_report(
                self.name,
                flags=[
                    flag(
                        "NO_POOL",
                        RiskSeverity.CRITICAL,
                        "No tradable pool found — the token cannot be traded.",
                    )
                ],
                insufficient_data=True,
            )

        flags = []
        positives = []
        dex = pool.dex.lower()
        liquidity = float(pool.liquidity_usd)
        facts: dict[str, object] = {
            "pool_address": pool.address,
            "dex": pool.dex,
            "liquidity_usd": liquidity,
        }

        if dex not in _KNOWN_DEXES:
            flags.append(
                flag(
                    "UNKNOWN_DEX",
                    RiskSeverity.HIGH,
                    f"Pool is on an unrecognised venue {pool.dex!r}.",
                )
            )
        else:
            positives.append(positive("KNOWN_DEX", f"Pool on recognised DEX {pool.dex}."))

        if liquidity <= _DUST_LIQUIDITY_USD:
            flags.append(
                flag(
                    "DUST_POOL",
                    RiskSeverity.CRITICAL,
                    f"Pool holds only ${liquidity:,.2f} — effectively empty.",
                )
            )

        # Abandoned: a pool with age but essentially no observed trading volume.
        volume = inputs.features.get("basic.volume")
        if volume is not None and inputs.age_minutes and inputs.age_minutes > 30:
            facts["volume_usd"] = volume
            if volume < _DUST_LIQUIDITY_USD:
                flags.append(
                    flag(
                        "POOL_ABANDONED",
                        RiskSeverity.HIGH,
                        "Pool exists but shows almost no trading — likely abandoned.",
                    )
                )

        return build_report(self.name, flags=flags, positives=positives, facts=facts)

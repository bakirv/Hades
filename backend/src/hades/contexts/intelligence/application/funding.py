"""Funding Analyzer — who paid for this wallet to exist?

The lineage of a wallet's SOL is a strong tell. Money straight from a CEX hot
wallet is ordinary; money from a known mixer, a blacklisted wallet, or a single
source that funds dozens of look-alike wallets is not. This analyzer classifies
each inbound funding edge and surfaces the suspicious ones, building the raw
material the Relationship and Cluster engines consume.

Pure: it classifies over the pre-fetched funder lists and known-address sets the
assembler supplies; it does no I/O itself.
"""

from __future__ import annotations

from hades.contexts.intelligence.domain.models import (
    FundingLink,
    FundingSourceKind,
    WalletObservationBatch,
)


class FundingAnalyzer:
    """Classifies inbound funding edges for a wallet."""

    def classify(
        self, funders: tuple[str, ...], batch: WalletObservationBatch
    ) -> tuple[FundingLink, ...]:
        links: list[FundingLink] = []
        for funder in funders:
            links.append(
                FundingLink(
                    source=funder, kind=self._kind(funder, batch), note=self._note(funder, batch)
                )
            )
        return tuple(links)

    def _kind(self, funder: str, batch: WalletObservationBatch) -> FundingSourceKind:
        if funder in batch.known_scammers:
            return FundingSourceKind.SUSPICIOUS
        if funder in batch.known_mixers:
            return FundingSourceKind.MIXER
        if funder in batch.known_exchanges:
            return FundingSourceKind.EXCHANGE
        return FundingSourceKind.WALLET

    def _note(self, funder: str, batch: WalletObservationBatch) -> str:
        if funder in batch.known_scammers:
            return "Funded by a blacklisted wallet."
        if funder in batch.known_mixers:
            return "Funded through a mixer."
        if funder in batch.known_exchanges:
            return "Funded from a known exchange."
        return ""

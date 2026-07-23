"""Domain events emitted by Wallet Intelligence."""

from __future__ import annotations

from hades.contexts.common.domain.value_objects import TokenRef
from hades.contexts.wallet.domain.models import WalletAssessment
from hades.shared_kernel.domain.events import DomainEvent


class WalletScoreComputed(DomainEvent):
    """Wallet-side analysis finished for a token."""

    aggregate_type: str = "token"
    token: TokenRef
    assessment: WalletAssessment

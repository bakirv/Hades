"""The assembler turns a SecurityScoreComputed into a wallet-observation batch."""

from __future__ import annotations

from datetime import UTC, datetime

from hades.contexts.common.domain.value_objects import Score, TokenMint, TokenRef
from hades.contexts.intelligence.domain.models import WalletRole
from hades.contexts.intelligence.infrastructure.assembler import WalletObservationAssembler
from hades.contexts.intelligence.infrastructure.chain_reader import InMemoryChainReader
from hades.contexts.security.domain.events import SecurityScoreComputed
from hades.contexts.security.domain.models import SecurityAssessment, SecurityDecision
from hades.shared_kernel.domain.identifiers import new_id

_DEPLOYER = "D" * 44
_H1 = "H" * 44
_FUNDER = "F" * 44


def _event(*, scammer: bool = False) -> SecurityScoreComputed:
    assessment = SecurityAssessment(
        token=TokenRef(mint=TokenMint(address="M" * 44)),
        decision=SecurityDecision.APPROVED,
        score=Score(value=80.0),
        facts={
            "developer": {"deployer": _DEPLOYER, "is_known_scammer": scammer},
            "holder": {"top_holders": [{"owner": _H1, "pct": 9.0}]},
        },
        analyzed_at=datetime.now(UTC),
    )
    return SecurityScoreComputed(
        aggregate_id=new_id(),
        token=assessment.token,
        assessment=assessment,
        vetoed=False,
    )


async def test_assembler_extracts_deployer_and_holders_from_facts() -> None:
    reader = InMemoryChainReader(funders={_DEPLOYER: [_FUNDER], _H1: [_FUNDER]})
    assembler = WalletObservationAssembler(reader=reader, live_lookups=True)
    batch = await assembler.build(_event())

    by_role = {o.role: o for o in batch.observations}
    assert by_role[WalletRole.DEPLOYER].address == _DEPLOYER
    assert by_role[WalletRole.HOLDER].address == _H1
    # Funders were enriched from the live reader.
    assert by_role[WalletRole.HOLDER].funders == (_FUNDER,)


async def test_assembler_marks_known_scammer_deployer() -> None:
    assembler = WalletObservationAssembler(reader=None, live_lookups=False)
    batch = await assembler.build(_event(scammer=True))
    deployer = next(o for o in batch.observations if o.role is WalletRole.DEPLOYER)
    assert deployer.is_known_scammer is True
    assert _DEPLOYER in batch.known_scammers
    # With live lookups off, no funders are fetched (degrades gracefully).
    assert all(o.funders == () for o in batch.observations)

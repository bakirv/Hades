"""End-to-end Security Engine: verdicts, veto, lists, persistence, events, learning."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from hades.contexts.common.domain.value_objects import TokenMint, TokenRef, WalletAddress
from hades.contexts.security.application.analyzers import DEFAULT_ANALYZERS
from hades.contexts.security.application.engine import SecurityEngine
from hades.contexts.security.application.lists import (
    BlacklistEngine,
    WhitelistEngine,
)
from hades.contexts.security.application.metrics import SecurityMetrics
from hades.contexts.security.application.scoring import SecurityScorer
from hades.contexts.security.domain.events import (
    SecurityScoreComputed,
    TokenApproved,
    TokenRejected,
)
from hades.contexts.security.domain.models import (
    ClusterReport,
    DeveloperReputation,
    HolderBalance,
    HoneypotProbe,
    LiquidityPool,
    MintAccount,
    SecurityInputs,
    TokenProgram,
)
from hades.contexts.security.infrastructure.developer_repository import (
    InMemoryDeveloperReputationStore,
)
from hades.contexts.security.infrastructure.list_registry import InMemoryListRegistry
from hades.contexts.security.infrastructure.security_repository import (
    InMemorySecurityRepository,
)
from hades.shared_kernel.events import InMemoryEventBus
from hades.shared_kernel.observability import MetricsRegistry

_MINT = "A" * 44
_DEPLOYER = "D" * 44
_SPL = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"


class _Harness:
    def __init__(self) -> None:
        self.bus = InMemoryEventBus()
        self.repo = InMemorySecurityRepository()
        self.dev = InMemoryDeveloperReputationStore()
        self.lists = InMemoryListRegistry()
        self.engine = SecurityEngine(
            analyzers=DEFAULT_ANALYZERS,
            scorer=SecurityScorer(min_security_score=60.0),
            blacklist=BlacklistEngine(self.lists),
            whitelist=WhitelistEngine(self.lists),
            repository=self.repo,
            developer_store=self.dev,
            event_bus=self.bus,
            metrics=SecurityMetrics(MetricsRegistry()),
        )


def _healthy_inputs(**over: object) -> SecurityInputs:
    mint = MintAccount(
        mint=_MINT,
        decimals=6,
        supply=Decimal(1_000_000),
        mint_authority=None,
        freeze_authority=None,
        owner_program=_SPL,
        program=TokenProgram.SPL_TOKEN,
    )
    holders = tuple(
        HolderBalance(owner=f"w{i}", amount=Decimal(5), pct=5.0) for i in range(20)
    )
    data: dict[str, object] = {
        "token": TokenRef(mint=TokenMint(address=_MINT)),
        "now": datetime.now(UTC),
        "mint_account": mint,
        "holders": holders,
        "holder_count": 500,
        "pool": LiquidityPool(
            address="pool1", dex="raydium", liquidity_usd=Decimal(50_000), lp_burned_pct=100.0
        ),
        "honeypot": HoneypotProbe(sellable=True, buy_tax_bps=50, sell_tax_bps=50),
        "developer": DeveloperReputation(deployer=_DEPLOYER, tokens_created=3, successes=3),
        "deployer": WalletAddress(address=_DEPLOYER),
        "cluster": ClusterReport(clusters=(), analysed_wallets=12),
        "features": {
            "basic.volume": 3000.0,
            "basic.buyers": 50.0,
            "basic.sellers": 40.0,
            "basic.trades_1h": 80.0,
            "holders.recurring_ratio": 0.2,
        },
    }
    data.update(over)
    return SecurityInputs(**data)  # type: ignore[arg-type]


async def test_healthy_token_is_approved_with_explanation() -> None:
    h = _Harness()
    approved: list[object] = []

    async def on_approved(event: object) -> None:
        approved.append(event)

    h.bus.subscribe(TokenApproved.__name__, on_approved)

    assessment = await h.engine.analyze(_healthy_inputs())

    assert assessment.approved
    assert assessment.score.value >= 70
    assert assessment.explanation is not None
    assert assessment.explanation.positives  # legible approval
    assert "authority" in assessment.sub_scores
    assert "rug_pull" in assessment.sub_scores
    assert len(approved) == 1


async def test_honeypot_is_rejected_vetoed_and_auto_blacklisted() -> None:
    h = _Harness()
    assessment = await h.engine.analyze(
        _healthy_inputs(honeypot=HoneypotProbe(sellable=False))
    )
    assert not assessment.approved
    assert assessment.has_critical_flag
    assert any(f.code == "CANNOT_SELL" for f in assessment.flags)
    # The engine auto-blacklists a confirmed honeypot token.
    assert await h.lists.is_blacklisted("token", _MINT)


async def test_active_authority_vetoes_regardless_of_health() -> None:
    h = _Harness()
    bad_mint = MintAccount(
        mint=_MINT,
        decimals=6,
        supply=Decimal(1_000_000),
        mint_authority="Z" * 44,
        freeze_authority="Z" * 44,
        owner_program=_SPL,
        program=TokenProgram.SPL_TOKEN,
    )
    assessment = await h.engine.analyze(_healthy_inputs(mint_account=bad_mint))
    assert not assessment.approved
    assert assessment.has_critical_flag


async def test_blacklisted_deployer_is_vetoed_before_analysis() -> None:
    h = _Harness()
    await h.lists.add_blacklist("deployer", _DEPLOYER, reason="prior rug")
    rejected: list[object] = []

    async def on_rejected(event: object) -> None:
        rejected.append(event)

    h.bus.subscribe(TokenRejected.__name__, on_rejected)

    assessment = await h.engine.analyze(_healthy_inputs())
    assert not assessment.approved
    assert any(f.code == "BLACKLISTED" for f in assessment.flags)
    assert len(rejected) == 1


async def test_whitelisted_token_waives_doubt() -> None:
    h = _Harness()
    await h.lists.add_whitelist("token", _MINT, reason="known project")
    # Strip most data so several analyzers run blind (doubt) yet score borderline.
    inputs = _healthy_inputs(
        holders=(),
        holder_count=None,
        honeypot=None,
        pool=None,
        developer=None,
    )
    assessment = await h.engine.analyze(inputs)
    assert any(p.code == "WHITELISTED" for p in assessment.positives)


async def test_rejected_assessments_are_persisted_for_research() -> None:
    h = _Harness()
    await h.engine.analyze(_healthy_inputs(honeypot=HoneypotProbe(sellable=False)))
    assert len(h.repo.saved) == 1
    assert not h.repo.saved[0].approved  # rejected tokens are stored too


async def test_security_score_computed_event_emitted() -> None:
    h = _Harness()
    events: list[SecurityScoreComputed] = []

    async def on_computed(event: object) -> None:
        assert isinstance(event, SecurityScoreComputed)
        events.append(event)

    h.bus.subscribe(SecurityScoreComputed.__name__, on_computed)
    await h.engine.analyze(_healthy_inputs())
    assert len(events) == 1
    assert events[0].assessment.approved


async def test_developer_reputation_accumulates() -> None:
    h = _Harness()
    await h.engine.analyze(_healthy_inputs())
    rep = await h.dev.get(WalletAddress(address=_DEPLOYER))
    assert rep is not None
    assert rep.tokens_created >= 1

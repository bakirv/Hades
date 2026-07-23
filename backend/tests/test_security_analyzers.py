"""Unit tests for the individual security analyzers (pure over SecurityInputs)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from hades.contexts.common.domain.value_objects import TokenMint, TokenRef
from hades.contexts.security.application.analyzers.authority import AuthorityAnalyzer
from hades.contexts.security.application.analyzers.behavior import BehaviorAnalyzer
from hades.contexts.security.application.analyzers.contract import ContractAnalyzer
from hades.contexts.security.application.analyzers.developer import DeveloperAnalyzer
from hades.contexts.security.application.analyzers.holder import (
    HolderAnalyzer,
    gini,
    hhi,
)
from hades.contexts.security.application.analyzers.honeypot import HoneypotAnalyzer
from hades.contexts.security.application.analyzers.liquidity import LiquidityAnalyzer
from hades.contexts.security.application.analyzers.pool import PoolAnalyzer
from hades.contexts.security.application.analyzers.transaction import TransactionAnalyzer
from hades.contexts.security.application.analyzers.wallet_cluster import (
    WalletClusterAnalyzer,
)
from hades.contexts.security.domain.models import (
    ClusterReport,
    DeveloperReputation,
    HolderBalance,
    HoneypotProbe,
    LiquidityPool,
    MintAccount,
    RiskSeverity,
    SecurityInputs,
    TokenProgram,
    WalletCluster,
)

_MINT = "A" * 44
_SPL = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"


def _inputs(**over: object) -> SecurityInputs:
    base: dict[str, object] = {
        "token": TokenRef(mint=TokenMint(address=_MINT)),
        "now": datetime.now(UTC),
    }
    base.update(over)
    return SecurityInputs(**base)  # type: ignore[arg-type]


def _clean_mint(**over: object) -> MintAccount:
    data: dict[str, object] = {
        "mint": _MINT,
        "decimals": 6,
        "supply": Decimal(1_000_000),
        "mint_authority": None,
        "freeze_authority": None,
        "owner_program": _SPL,
        "program": TokenProgram.SPL_TOKEN,
    }
    data.update(over)
    return MintAccount(**data)  # type: ignore[arg-type]


def _codes(report: object) -> set[str]:
    return {f.code for f in report.flags}  # type: ignore[attr-defined]


# -- Gini / HHI math ----------------------------------------------------------


def test_gini_perfect_equality_is_zero() -> None:
    assert gini([10.0, 10.0, 10.0, 10.0]) < 1e-9


def test_gini_extreme_inequality_high() -> None:
    # One whale, many dust holders — inequality near the top of the range.
    assert gini([97.0, 1.0, 1.0, 1.0]) > 0.7


def test_hhi_single_holder_is_one() -> None:
    assert abs(hhi([100.0]) - 1.0) < 1e-9


def test_hhi_dispersed_is_low() -> None:
    assert hhi([1.0] * 100) < 0.02


# -- Contract -----------------------------------------------------------------


def test_contract_flags_unreadable_mint_as_critical() -> None:
    report = ContractAnalyzer().analyze(_inputs(mint_account=None))
    assert report.insufficient_data
    assert "MINT_ACCOUNT_UNREADABLE" in _codes(report)
    assert report.score.value == 0.0


def test_contract_token2022_risky_extension_is_critical() -> None:
    mint = _clean_mint(
        owner_program="TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
        program=TokenProgram.TOKEN_2022,
        extensions=("transfer_hook",),
    )
    report = ContractAnalyzer().analyze(_inputs(mint_account=mint))
    assert "TOKEN2022_RISKY_EXTENSION" in _codes(report)
    assert report.score.value == 0.0


def test_contract_standard_spl_is_clean() -> None:
    report = ContractAnalyzer().analyze(_inputs(mint_account=_clean_mint()))
    assert report.score.value > 90
    assert any(p.code == "STANDARD_SPL_TOKEN" for p in report.positives)


# -- Authority ----------------------------------------------------------------


def test_authority_active_mint_and_freeze_are_critical() -> None:
    mint = _clean_mint(mint_authority="B" * 44, freeze_authority="C" * 44)
    report = AuthorityAnalyzer().analyze(_inputs(mint_account=mint))
    assert {"MINT_AUTHORITY_ACTIVE", "FREEZE_AUTHORITY_ACTIVE"} <= _codes(report)
    assert report.score.value == 0.0


def test_authority_renounced_scores_high_with_positives() -> None:
    report = AuthorityAnalyzer().analyze(_inputs(mint_account=_clean_mint()))
    assert report.score.value == 100.0
    codes = {p.code for p in report.positives}
    assert {"MINT_RENOUNCED", "FREEZE_RENOUNCED"} <= codes


def test_authority_mutable_metadata_flagged() -> None:
    report = AuthorityAnalyzer().analyze(
        _inputs(mint_account=_clean_mint(), is_mutable=True)
    )
    assert "METADATA_MUTABLE" in _codes(report)


# -- Liquidity ----------------------------------------------------------------


def test_liquidity_insufficient_is_critical() -> None:
    pool = LiquidityPool(
        address="p", dex="raydium", liquidity_usd=Decimal(1000), lp_burned_pct=100.0
    )
    report = LiquidityAnalyzer().analyze(_inputs(pool=pool))
    assert "INSUFFICIENT_LIQUIDITY" in _codes(report)
    assert report.score.value == 0.0


def test_liquidity_unlocked_lp_flagged() -> None:
    pool = LiquidityPool(
        address="p", dex="raydium", liquidity_usd=Decimal(50_000), lp_burned_pct=0.0
    )
    report = LiquidityAnalyzer().analyze(_inputs(pool=pool))
    assert "LP_NOT_SECURED" in _codes(report)


def test_liquidity_healthy_and_burned_scores_well() -> None:
    pool = LiquidityPool(
        address="p", dex="raydium", liquidity_usd=Decimal(50_000), lp_burned_pct=100.0
    )
    report = LiquidityAnalyzer().analyze(_inputs(pool=pool))
    assert report.score.value >= 90
    assert {p.code for p in report.positives} >= {"HEALTHY_LIQUIDITY", "LP_SECURED"}


def test_liquidity_unknown_lock_is_doubt() -> None:
    pool = LiquidityPool(address="p", dex="raydium", liquidity_usd=Decimal(50_000))
    report = LiquidityAnalyzer().analyze(_inputs(pool=pool))
    assert "LP_LOCK_UNKNOWN" in _codes(report)


# -- Pool ---------------------------------------------------------------------


def test_pool_missing_is_critical() -> None:
    report = PoolAnalyzer().analyze(_inputs(pool=None))
    assert "NO_POOL" in _codes(report)
    assert report.insufficient_data


def test_pool_unknown_dex_flagged() -> None:
    pool = LiquidityPool(address="p", dex="shadydex", liquidity_usd=Decimal(20_000))
    report = PoolAnalyzer().analyze(_inputs(pool=pool))
    assert "UNKNOWN_DEX" in _codes(report)


# -- Holder -------------------------------------------------------------------


def test_holder_single_wallet_majority_is_critical() -> None:
    holders = [HolderBalance(owner="w1", amount=Decimal(60), pct=60.0)]
    report = HolderAnalyzer().analyze(_inputs(holders=tuple(holders)))
    assert "SINGLE_WALLET_MAJORITY" in _codes(report)
    assert report.score.value == 0.0


def test_holder_healthy_distribution_positive() -> None:
    holders = tuple(
        HolderBalance(owner=f"w{i}", amount=Decimal(5), pct=5.0) for i in range(20)
    )
    report = HolderAnalyzer().analyze(_inputs(holders=holders, holder_count=500))
    assert any(p.code == "HEALTHY_DISTRIBUTION" for p in report.positives)
    assert "top1_pct" in report.facts


def test_holder_excludes_pool_vault() -> None:
    pool = LiquidityPool(address="vault", dex="raydium", liquidity_usd=Decimal(50_000))
    holders = (
        HolderBalance(owner="vault", amount=Decimal(90), pct=90.0),
        HolderBalance(owner="w1", amount=Decimal(5), pct=5.0),
        HolderBalance(owner="w2", amount=Decimal(5), pct=5.0),
    )
    report = HolderAnalyzer().analyze(_inputs(holders=holders, pool=pool))
    # The 90% vault holder is excluded, so no majority flag.
    assert "SINGLE_WALLET_MAJORITY" not in _codes(report)


# -- Honeypot -----------------------------------------------------------------


def test_honeypot_cannot_sell_is_critical() -> None:
    report = HoneypotAnalyzer().analyze(
        _inputs(honeypot=HoneypotProbe(sellable=False))
    )
    assert "CANNOT_SELL" in _codes(report)
    assert report.score.value == 0.0


def test_honeypot_unverified_is_doubt() -> None:
    report = HoneypotAnalyzer().analyze(_inputs(honeypot=None))
    assert report.insufficient_data
    assert "HONEYPOT_UNVERIFIED" in _codes(report)


def test_honeypot_punitive_tax_is_critical() -> None:
    probe = HoneypotProbe(sellable=True, buy_tax_bps=100, sell_tax_bps=5000)
    report = HoneypotAnalyzer().analyze(_inputs(honeypot=probe))
    assert "PUNITIVE_SELL_TAX" in _codes(report)


def test_honeypot_sellable_clean_positive() -> None:
    probe = HoneypotProbe(sellable=True, buy_tax_bps=50, sell_tax_bps=50)
    report = HoneypotAnalyzer().analyze(_inputs(honeypot=probe))
    assert any(p.code == "SELLABLE_VERIFIED" for p in report.positives)


# -- Developer ----------------------------------------------------------------


def test_developer_unknown_is_doubt_not_veto() -> None:
    report = DeveloperAnalyzer().analyze(_inputs(developer=None))
    assert report.insufficient_data
    assert report.score.value > 0  # unknown is a mild penalty, not a veto


def test_developer_known_scammer_is_critical() -> None:
    rep = DeveloperReputation(deployer="d", tokens_created=3, is_known_scammer=True)
    report = DeveloperAnalyzer().analyze(_inputs(developer=rep))
    assert "KNOWN_SCAMMER" in _codes(report)
    assert report.score.value == 0.0


def test_developer_serial_rugger_is_critical() -> None:
    rep = DeveloperReputation(deployer="d", tokens_created=4, rugs=3)
    report = DeveloperAnalyzer().analyze(_inputs(developer=rep))
    assert "SERIAL_RUGGER" in _codes(report)


def test_developer_proven_is_positive() -> None:
    rep = DeveloperReputation(deployer="d", tokens_created=3, successes=3)
    report = DeveloperAnalyzer().analyze(_inputs(developer=rep))
    assert any(p.code == "PROVEN_DEVELOPER" for p in report.positives)


# -- Wallet cluster -----------------------------------------------------------


def test_cluster_controlling_supply_is_critical() -> None:
    cluster = WalletCluster(members=("a", "b", "c"), funder="f", pct_supply=45.0)
    report = WalletClusterAnalyzer().analyze(
        _inputs(cluster=ClusterReport(clusters=(cluster,), analysed_wallets=10))
    )
    assert "CLUSTER_CONTROLS_SUPPLY" in _codes(report)
    assert report.score.value == 0.0


def test_cluster_none_found_positive() -> None:
    report = WalletClusterAnalyzer().analyze(
        _inputs(cluster=ClusterReport(clusters=(), analysed_wallets=10))
    )
    assert any(p.code == "NO_CLUSTERS" for p in report.positives)


# -- Transaction / Behavior ---------------------------------------------------


def test_transaction_wash_trading_flagged() -> None:
    report = TransactionAnalyzer().analyze(
        _inputs(features={"basic.volume": 100_000.0, "basic.buyers": 2.0})
    )
    assert "WASH_TRADING_SUSPECTED" in _codes(report)


def test_transaction_no_data_is_info() -> None:
    report = TransactionAnalyzer().analyze(_inputs(features={}))
    assert report.insufficient_data
    assert report.flags[0].severity is RiskSeverity.INFO


def test_behavior_no_sellers_flagged() -> None:
    report = BehaviorAnalyzer().analyze(
        _inputs(
            features={"basic.buyers": 50.0, "basic.sellers": 0.0, "basic.trades_1h": 60.0}
        )
    )
    assert "NO_SELLERS" in _codes(report)


def test_behavior_too_early_is_neutral() -> None:
    report = BehaviorAnalyzer().analyze(
        _inputs(
            features={"basic.buyers": 3.0, "basic.sellers": 1.0, "basic.trades_1h": 4.0}
        )
    )
    assert report.insufficient_data
    assert "TOO_EARLY_TO_JUDGE" in _codes(report)

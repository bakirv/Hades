"""Security scorer: aggregation, critical veto, doubt rule, rug-pull composite."""

from __future__ import annotations

from hades.contexts.common.domain.value_objects import Score
from hades.contexts.security.application.scoring import SecurityScorer
from hades.contexts.security.domain.models import (
    AnalyzerReport,
    RiskFlag,
    RiskSeverity,
    SecurityDecision,
)


def _report(
    name: str,
    value: float,
    *,
    flags: tuple[RiskFlag, ...] = (),
    insufficient: bool = False,
) -> AnalyzerReport:
    return AnalyzerReport(
        name=name,
        score=Score(value=value),
        flags=flags,
        insufficient_data=insufficient,
    )


def _clean_reports() -> list[AnalyzerReport]:
    names = (
        "contract",
        "authority",
        "liquidity",
        "pool",
        "holder",
        "honeypot",
        "developer",
        "wallet_cluster",
        "transaction",
        "behavior",
    )
    return [_report(n, 95.0) for n in names]


def test_clean_token_is_approved() -> None:
    result = SecurityScorer().score(_clean_reports())
    assert result.decision is SecurityDecision.APPROVED
    assert result.final.value >= 90
    assert "rug_pull" in result.sub_scores
    assert not result.vetoed


def test_single_critical_flag_vetoes() -> None:
    reports = _clean_reports()
    reports[1] = _report(
        "authority",
        0.0,
        flags=(
            RiskFlag(
                code="FREEZE_AUTHORITY_ACTIVE",
                severity=RiskSeverity.CRITICAL,
                detail="freeze active",
            ),
        ),
    )
    result = SecurityScorer().score(reports)
    assert result.decision is SecurityDecision.REJECTED
    assert result.vetoed
    assert result.final.value <= 5.0
    assert "FREEZE_AUTHORITY_ACTIVE" in result.reject_reasons


def test_below_min_score_rejected() -> None:
    result = SecurityScorer(min_security_score=90.0).score(
        [_report(n, 70.0) for n in ("contract", "authority", "liquidity")]
    )
    assert result.decision is SecurityDecision.REJECTED
    assert "BELOW_MIN_SECURITY_SCORE" in result.reject_reasons


def test_doubt_rule_rejects_borderline_blind_token() -> None:
    reports = [
        _report("contract", 65.0),
        _report("authority", 65.0),
        _report("liquidity", 65.0, insufficient=True),
        _report("holder", 65.0, insufficient=True),
        _report("honeypot", 65.0, insufficient=True),
    ]
    result = SecurityScorer(
        min_security_score=60.0, max_insufficient_analyzers=3, doubt_buffer=15.0
    ).score(reports)
    assert result.decision is SecurityDecision.REJECTED
    assert "INSUFFICIENT_DATA_CONFIDENCE" in result.reject_reasons


def test_trusted_waives_doubt_but_not_critical() -> None:
    reports = [
        _report("contract", 65.0),
        _report("liquidity", 65.0, insufficient=True),
        _report("holder", 65.0, insufficient=True),
        _report("honeypot", 65.0, insufficient=True),
    ]
    trusted = SecurityScorer(min_security_score=60.0).score(reports, trusted=True)
    assert trusted.decision is SecurityDecision.APPROVED
    # A critical still vetoes even when trusted.
    reports[0] = _report(
        "contract",
        0.0,
        flags=(RiskFlag(code="X", severity=RiskSeverity.CRITICAL, detail="bad"),),
    )
    vetoed = SecurityScorer(min_security_score=60.0).score(reports, trusted=True)
    assert vetoed.decision is SecurityDecision.REJECTED


def test_rug_pull_dragged_down_by_weakest_dimension() -> None:
    reports = _clean_reports()
    reports[2] = _report("liquidity", 0.0)  # liquidity is a rug dimension
    result = SecurityScorer().score(reports)
    # rug_pull must reflect the weak liquidity, not average it away.
    assert result.sub_scores["rug_pull"] < 70

"""Research Lab records and the opportunity ledger.

Research operates offline on copied data and has **no path to execution**; these
tables store its jobs/experiments. ``accepted_opportunities`` and
``rejected_opportunities`` record every discovery decision (and *why*) so the
funnel is fully auditable.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hades.shared_kernel.persistence.database import Base
from hades.shared_kernel.persistence.models._mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ResearchJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A queued/running/finished offline research job."""

    __tablename__ = "research_jobs"

    name: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    kind: Mapped[str | None] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True, nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)


class Experiment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single experiment within a research job, with its metrics/conclusion."""

    __tablename__ = "experiments"

    research_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_jobs.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    hypothesis: Mapped[str | None] = mapped_column(Text)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True, nullable=False)
    candidate_strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("strategies.id", ondelete="SET NULL"), index=True
    )
    conclusion: Mapped[str | None] = mapped_column(Text)


class AcceptedOpportunity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A token that passed the funnel and was accepted for (paper/live) action."""

    __tablename__ = "accepted_opportunities"

    token_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tokens.id", ondelete="CASCADE"), index=True, nullable=False
    )
    signal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("signals.id", ondelete="SET NULL"), index=True
    )
    mode: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    score: Mapped[float | None] = mapped_column(Float)
    reason: Mapped[str | None] = mapped_column(Text)
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )


class RejectedOpportunity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A token that was rejected, with the gate/stage and reason it failed."""

    __tablename__ = "rejected_opportunities"

    token_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tokens.id", ondelete="SET NULL"), index=True
    )
    mint: Mapped[str | None] = mapped_column(String(64), index=True)
    stage: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    score: Mapped[float | None] = mapped_column(Float)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    rejected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )


# =============================================================================
# Research Lab records — append-only knowledge, never a path to execution.
#
# Each table keeps queryable scalar columns plus a JSONB ``payload`` holding the
# full domain object (the same shape the API returns), mirroring how the AI
# Committee persists its predictions. Nothing here can trade; these are the lab's
# permanent memory of experiments, studies, candidates, comparisons and decisions.
# =============================================================================


class ResearchExperimentRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A finished Research-Lab experiment and its reproducible metric set."""

    __tablename__ = "research_experiments"

    experiment_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    hypothesis: Mapped[str | None] = mapped_column(Text)
    conclusion: Mapped[str | None] = mapped_column(Text)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)


class ResearchBacktestRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A backtest run over a historical window, scored net of frictions."""

    __tablename__ = "research_backtests"

    backtest_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    strategy: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    total_return: Mapped[float | None] = mapped_column(Float)
    sharpe: Mapped[float | None] = mapped_column(Float)
    max_drawdown: Mapped[float | None] = mapped_column(Float)
    profit_factor: Mapped[float | None] = mapped_column(Float)
    trades: Mapped[int | None] = mapped_column(Integer)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class ResearchCandidateRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A candidate strategy the lab is developing (a rule genome, never code)."""

    __tablename__ = "research_candidates"

    candidate_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    archetype: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    stage: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class ResearchShadowRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A shadow strategy's latest virtual-ledger snapshot (no capital, no orders)."""

    __tablename__ = "research_shadows"

    shadow_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    archetype: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class ResearchPromotionRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A promotion decision — a recommendation only; never a deployment."""

    __tablename__ = "research_promotions"

    candidate_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    candidate_name: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    manual_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class ResearchReportRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A generated periodic research report, stored for future consultation."""

    __tablename__ = "research_reports"

    report_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    period: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class ResearchKnowledgeRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An append-only Knowledge-Base entry. History is never deleted."""

    __tablename__ = "research_knowledge"

    entry_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class ResearchHypothesisRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A recorded research hypothesis and how it resolved (open/confirmed/refuted)."""

    __tablename__ = "research_hypotheses"

    hypothesis_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

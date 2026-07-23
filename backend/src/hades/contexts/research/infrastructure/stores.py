"""Persistence adapters for the Research Lab — in-memory + PostgreSQL.

In-memory stores back tests and single-process runs; the Postgres ones back real
deployments. Everything is append-only (or upsert-latest for shadows/candidates)
in the spirit of the rest of Hades: the research funnel is never rewritten, so the
knowledge trail is complete for years.

Each Postgres store serialises the full domain object into a JSONB ``payload`` and
rebuilds it with pydantic, exactly like the AI Committee's stores.
"""

from __future__ import annotations

from collections import deque

from sqlalchemy import desc, select

from hades.contexts.research.domain.models import (
    BacktestResult,
    CandidateStrategy,
    ExperimentResult,
    Hypothesis,
    KnowledgeEntry,
    PromotionDecision,
    ResearchReport,
    ShadowStrategy,
)
from hades.shared_kernel.persistence.database import Database
from hades.shared_kernel.persistence.models.research import (
    ResearchBacktestRecord,
    ResearchCandidateRecord,
    ResearchExperimentRecord,
    ResearchHypothesisRecord,
    ResearchKnowledgeRecord,
    ResearchPromotionRecord,
    ResearchReportRecord,
    ResearchShadowRecord,
)

# =============================================================================
# In-memory
# =============================================================================


class InMemoryExperimentStore:
    def __init__(self, maxlen: int = 1000) -> None:
        self._ring: deque[ExperimentResult] = deque(maxlen=maxlen)

    async def save(self, result: ExperimentResult) -> None:
        self._ring.append(result)

    async def recent(self, limit: int = 50) -> tuple[ExperimentResult, ...]:
        return tuple(list(reversed(self._ring))[:limit])


class InMemoryBacktestStore:
    def __init__(self, maxlen: int = 1000) -> None:
        self._ring: deque[BacktestResult] = deque(maxlen=maxlen)

    async def save(self, result: BacktestResult) -> None:
        self._ring.append(result)

    async def recent(self, limit: int = 50) -> tuple[BacktestResult, ...]:
        return tuple(list(reversed(self._ring))[:limit])


class InMemoryCandidateStore:
    def __init__(self) -> None:
        self._by_id: dict[str, CandidateStrategy] = {}

    async def save(self, candidate: CandidateStrategy) -> None:
        self._by_id[str(candidate.candidate_id)] = candidate

    async def get(self, candidate_id: str) -> CandidateStrategy | None:
        return self._by_id.get(candidate_id)

    async def all(self) -> tuple[CandidateStrategy, ...]:
        return tuple(self._by_id.values())


class InMemoryShadowStore:
    def __init__(self) -> None:
        self._by_id: dict[str, ShadowStrategy] = {}

    async def save(self, shadow: ShadowStrategy) -> None:
        self._by_id[str(shadow.shadow_id)] = shadow

    async def all(self) -> tuple[ShadowStrategy, ...]:
        return tuple(self._by_id.values())


class InMemoryPromotionStore:
    def __init__(self, maxlen: int = 1000) -> None:
        self._ring: deque[PromotionDecision] = deque(maxlen=maxlen)

    async def save(self, decision: PromotionDecision) -> None:
        self._ring.append(decision)

    async def recent(self, limit: int = 50) -> tuple[PromotionDecision, ...]:
        return tuple(list(reversed(self._ring))[:limit])


class InMemoryReportStore:
    def __init__(self, maxlen: int = 500) -> None:
        self._ring: deque[ResearchReport] = deque(maxlen=maxlen)

    async def save(self, report: ResearchReport) -> None:
        self._ring.append(report)

    async def recent(self, limit: int = 50) -> tuple[ResearchReport, ...]:
        return tuple(list(reversed(self._ring))[:limit])


class InMemoryKnowledgeStore:
    def __init__(self, maxlen: int = 100_000) -> None:
        self._entries: deque[KnowledgeEntry] = deque(maxlen=maxlen)
        self._hypotheses: deque[Hypothesis] = deque(maxlen=maxlen)

    async def append(self, entry: KnowledgeEntry) -> None:
        self._entries.append(entry)

    async def append_hypothesis(self, hypothesis: Hypothesis) -> None:
        self._hypotheses.append(hypothesis)

    async def recent(self, limit: int = 100) -> tuple[KnowledgeEntry, ...]:
        return tuple(list(reversed(self._entries))[:limit])

    async def hypotheses(self, limit: int = 100) -> tuple[Hypothesis, ...]:
        return tuple(list(reversed(self._hypotheses))[:limit])


# =============================================================================
# PostgreSQL (append-only; JSONB payload holds the full domain object)
# =============================================================================


class PostgresExperimentStore:
    def __init__(self, database: Database) -> None:
        self._db = database

    async def save(self, result: ExperimentResult) -> None:
        async with self._db.session() as session:
            session.add(
                ResearchExperimentRecord(
                    experiment_id=str(result.experiment_id),
                    name=result.name,
                    kind=result.kind.value,
                    status=result.status.value,
                    hypothesis=result.hypothesis,
                    conclusion=result.conclusion,
                    metrics=result.metrics,
                    error=result.error,
                )
            )

    async def recent(self, limit: int = 50) -> tuple[ExperimentResult, ...]:
        async with self._db.session() as session:
            rows = (
                await session.scalars(
                    select(ResearchExperimentRecord)
                    .order_by(desc(ResearchExperimentRecord.created_at))
                    .limit(min(limit, 500))
                )
            ).all()
        return tuple(
            ExperimentResult(
                experiment_id=r.experiment_id,
                name=r.name,
                kind=r.kind,
                status=r.status,
                metrics=r.metrics,
                conclusion=r.conclusion or "",
                hypothesis=r.hypothesis or "",
                error=r.error,
            )
            for r in rows
        )


class PostgresBacktestStore:
    def __init__(self, database: Database) -> None:
        self._db = database

    async def save(self, result: BacktestResult) -> None:
        async with self._db.session() as session:
            session.add(
                ResearchBacktestRecord(
                    backtest_id=str(result.backtest_id),
                    strategy=result.strategy,
                    total_return=result.metrics.total_return,
                    sharpe=result.metrics.sharpe,
                    max_drawdown=result.metrics.max_drawdown,
                    profit_factor=result.metrics.profit_factor,
                    trades=result.metrics.trades,
                    payload=result.model_dump(mode="json"),
                )
            )

    async def recent(self, limit: int = 50) -> tuple[BacktestResult, ...]:
        async with self._db.session() as session:
            rows = (
                await session.scalars(
                    select(ResearchBacktestRecord)
                    .order_by(desc(ResearchBacktestRecord.created_at))
                    .limit(min(limit, 500))
                )
            ).all()
        return tuple(BacktestResult.model_validate(r.payload) for r in rows if r.payload)


class PostgresCandidateStore:
    def __init__(self, database: Database) -> None:
        self._db = database

    async def save(self, candidate: CandidateStrategy) -> None:
        async with self._db.session() as session:
            session.add(
                ResearchCandidateRecord(
                    candidate_id=str(candidate.candidate_id),
                    name=candidate.name,
                    archetype=candidate.archetype.value,
                    version=candidate.version,
                    stage=candidate.stage.value,
                    payload=candidate.model_dump(mode="json"),
                )
            )

    async def get(self, candidate_id: str) -> CandidateStrategy | None:
        async with self._db.session() as session:
            row = await session.scalar(
                select(ResearchCandidateRecord)
                .where(ResearchCandidateRecord.candidate_id == candidate_id)
                .order_by(desc(ResearchCandidateRecord.created_at))
                .limit(1)
            )
        return CandidateStrategy.model_validate(row.payload) if row and row.payload else None

    async def all(self) -> tuple[CandidateStrategy, ...]:
        async with self._db.session() as session:
            rows = (
                await session.scalars(
                    select(ResearchCandidateRecord).order_by(
                        desc(ResearchCandidateRecord.created_at)
                    )
                )
            ).all()
        return tuple(CandidateStrategy.model_validate(r.payload) for r in rows if r.payload)


class PostgresShadowStore:
    def __init__(self, database: Database) -> None:
        self._db = database

    async def save(self, shadow: ShadowStrategy) -> None:
        async with self._db.session() as session:
            session.add(
                ResearchShadowRecord(
                    shadow_id=str(shadow.shadow_id),
                    name=shadow.name,
                    archetype=shadow.archetype.value,
                    payload=shadow.model_dump(mode="json"),
                )
            )

    async def all(self) -> tuple[ShadowStrategy, ...]:
        async with self._db.session() as session:
            rows = (
                await session.scalars(
                    select(ResearchShadowRecord).order_by(desc(ResearchShadowRecord.created_at))
                )
            ).all()
        # Latest snapshot per shadow_id.
        latest: dict[str, ShadowStrategy] = {}
        for r in rows:
            if r.payload and r.shadow_id not in latest:
                latest[r.shadow_id] = ShadowStrategy.model_validate(r.payload)
        return tuple(latest.values())


class PostgresPromotionStore:
    def __init__(self, database: Database) -> None:
        self._db = database

    async def save(self, decision: PromotionDecision) -> None:
        async with self._db.session() as session:
            session.add(
                ResearchPromotionRecord(
                    candidate_id=str(decision.candidate_id),
                    candidate_name=decision.candidate_name,
                    kind=decision.kind.value,
                    outcome=decision.outcome.value,
                    manual_approved=decision.manual_approved,
                    rationale=decision.rationale,
                    payload=decision.model_dump(mode="json"),
                )
            )

    async def recent(self, limit: int = 50) -> tuple[PromotionDecision, ...]:
        async with self._db.session() as session:
            rows = (
                await session.scalars(
                    select(ResearchPromotionRecord)
                    .order_by(desc(ResearchPromotionRecord.created_at))
                    .limit(min(limit, 500))
                )
            ).all()
        return tuple(PromotionDecision.model_validate(r.payload) for r in rows if r.payload)


class PostgresReportStore:
    def __init__(self, database: Database) -> None:
        self._db = database

    async def save(self, report: ResearchReport) -> None:
        async with self._db.session() as session:
            session.add(
                ResearchReportRecord(
                    report_id=str(report.report_id),
                    period=report.period,
                    title=report.title,
                    summary=report.summary,
                    payload=report.model_dump(mode="json"),
                )
            )

    async def recent(self, limit: int = 50) -> tuple[ResearchReport, ...]:
        async with self._db.session() as session:
            rows = (
                await session.scalars(
                    select(ResearchReportRecord)
                    .order_by(desc(ResearchReportRecord.created_at))
                    .limit(min(limit, 200))
                )
            ).all()
        return tuple(ResearchReport.model_validate(r.payload) for r in rows if r.payload)


class PostgresKnowledgeStore:
    def __init__(self, database: Database) -> None:
        self._db = database

    async def append(self, entry: KnowledgeEntry) -> None:
        async with self._db.session() as session:
            session.add(
                ResearchKnowledgeRecord(
                    entry_id=str(entry.entry_id),
                    category=entry.category,
                    title=entry.title,
                    body=entry.body,
                    data={k: str(v) for k, v in entry.data.items()},
                )
            )

    async def append_hypothesis(self, hypothesis: Hypothesis) -> None:
        async with self._db.session() as session:
            session.add(
                ResearchHypothesisRecord(
                    hypothesis_id=str(hypothesis.hypothesis_id),
                    statement=hypothesis.statement,
                    status=hypothesis.status,
                    rationale=hypothesis.rationale,
                    evidence=hypothesis.evidence,
                )
            )

    async def recent(self, limit: int = 100) -> tuple[KnowledgeEntry, ...]:
        async with self._db.session() as session:
            rows = (
                await session.scalars(
                    select(ResearchKnowledgeRecord)
                    .order_by(desc(ResearchKnowledgeRecord.created_at))
                    .limit(min(limit, 1000))
                )
            ).all()
        return tuple(
            KnowledgeEntry(
                entry_id=r.entry_id,
                category=r.category,
                title=r.title,
                body=r.body or "",
                data=dict(r.data or {}),
            )
            for r in rows
        )

    async def hypotheses(self, limit: int = 100) -> tuple[Hypothesis, ...]:
        async with self._db.session() as session:
            rows = (
                await session.scalars(
                    select(ResearchHypothesisRecord)
                    .order_by(desc(ResearchHypothesisRecord.created_at))
                    .limit(min(limit, 1000))
                )
            ).all()
        return tuple(
            Hypothesis(
                hypothesis_id=r.hypothesis_id,
                statement=r.statement,
                rationale=r.rationale or "",
                status=r.status,
                evidence=dict(r.evidence or {}),
            )
            for r in rows
        )

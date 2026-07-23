"""Knowledge Base — the lab's permanent, append-only memory.

Everything is kept forever: experiments, results, hypotheses, errors, conclusions,
datasets, comparisons. Nothing is ever deleted — the whole point is that the lab
learns across years, so a refuted idea is as valuable as a confirmed one. This is a
thin application service over an append-only :class:`KnowledgeStore`.
"""

from __future__ import annotations

from hades.contexts.research.domain.models import (
    ExperimentResult,
    Hypothesis,
    KnowledgeEntry,
    PromotionDecision,
    StrategyComparison,
)
from hades.contexts.research.domain.ports import KnowledgeStore


class KnowledgeBase:
    """Application service that records — never removes — research knowledge."""

    def __init__(self, store: KnowledgeStore) -> None:
        self._store = store

    async def record_experiment(self, result: ExperimentResult) -> None:
        await self._store.append(
            KnowledgeEntry(
                category="experiment",
                title=f"{result.name} ({result.kind.value})",
                body=result.conclusion or result.hypothesis,
                data=dict(result.metrics),
            )
        )

    async def record_conclusion(
        self, title: str, body: str, data: dict[str, float] | None = None
    ) -> None:
        await self._store.append(
            KnowledgeEntry(category="conclusion", title=title, body=body, data=dict(data or {}))
        )

    async def record_error(self, title: str, body: str) -> None:
        await self._store.append(KnowledgeEntry(category="error", title=title, body=body))

    async def record_comparison(self, comparison: StrategyComparison) -> None:
        await self._store.append(
            KnowledgeEntry(
                category="comparison",
                title=f"strategy comparison on {comparison.objective}",
                body=" > ".join(comparison.ranking),
            )
        )

    async def record_promotion(self, decision: PromotionDecision) -> None:
        await self._store.append(
            KnowledgeEntry(
                category="conclusion",
                title=f"promotion {decision.outcome.value}: {decision.candidate_name}",
                body=decision.rationale,
            )
        )

    async def add_hypothesis(self, hypothesis: Hypothesis) -> None:
        await self._store.append_hypothesis(hypothesis)

    async def resolve_hypothesis(
        self, hypothesis: Hypothesis, *, confirmed: bool, evidence: dict[str, float] | None = None
    ) -> Hypothesis:
        resolved = hypothesis.model_copy(
            update={
                "status": "confirmed" if confirmed else "refuted",
                "evidence": dict(evidence or {}),
            }
        )
        await self._store.append_hypothesis(resolved)
        return resolved

    async def recent(self, limit: int = 100) -> tuple[KnowledgeEntry, ...]:
        return await self._store.recent(limit)

    async def hypotheses(self, limit: int = 100) -> tuple[Hypothesis, ...]:
        return await self._store.hypotheses(limit)

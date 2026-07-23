"""Report Generator — daily / weekly / monthly research digests.

Rolls the lab's recent activity into a stored, human-readable report: experiments
run, strategy and model comparisons, new features proposed, promotions decided.
Reports are persisted (never thrown away) so the research narrative is
consultable years later. Generation is pure given its inputs.
"""

from __future__ import annotations

from collections.abc import Sequence

from hades.contexts.research.domain.models import (
    ExperimentResult,
    FeatureProposal,
    PromotionDecision,
    ResearchReport,
    StrategyComparison,
)


class ReportGenerator:
    """Builds a :class:`ResearchReport` from recent lab activity."""

    def generate(
        self,
        *,
        period: str,
        experiments: Sequence[ExperimentResult] = (),
        comparison: StrategyComparison | None = None,
        proposals: Sequence[FeatureProposal] = (),
        promotions: Sequence[PromotionDecision] = (),
    ) -> ResearchReport:
        finished = [e for e in experiments if e.status.value == "finished"]
        failed = [e for e in experiments if e.status.value == "failed"]

        sections: dict[str, str] = {}
        sections["experiments"] = self._experiments_section(experiments)
        if comparison is not None:
            sections["strategy_ranking"] = " > ".join(comparison.ranking) or "no strategies ranked"
        if proposals:
            sections["feature_proposals"] = "\n".join(
                f"- {p.action}: {p.feature} (importance={p.importance})" for p in proposals
            )
        if promotions:
            sections["promotions"] = "\n".join(
                f"- {d.outcome.value}: {d.candidate_name} — {d.rationale}" for d in promotions
            )

        stats = {
            "experiments_total": float(len(experiments)),
            "experiments_finished": float(len(finished)),
            "experiments_failed": float(len(failed)),
            "features_proposed": float(len(proposals)),
            "promotions_approved": float(
                sum(1 for d in promotions if d.outcome.value == "approved")
            ),
            "promotions_rejected": float(
                sum(1 for d in promotions if d.outcome.value == "rejected")
            ),
        }
        summary = (
            f"{period.capitalize()} research digest: {len(finished)} experiments finished, "
            f"{len(proposals)} feature proposals, "
            f"{int(stats['promotions_approved'])} promotions recommended "
            f"(none deployed automatically)."
        )
        return ResearchReport(
            period=period,
            title=f"{period.capitalize()} Research Report",
            summary=summary,
            sections=sections,
            stats=stats,
        )

    @staticmethod
    def _experiments_section(experiments: Sequence[ExperimentResult]) -> str:
        if not experiments:
            return "no experiments this period"
        lines = []
        for e in experiments[:20]:
            headline = e.conclusion or e.hypothesis or "—"
            lines.append(f"- [{e.kind.value}] {e.name}: {e.status.value} — {headline}")
        return "\n".join(lines)

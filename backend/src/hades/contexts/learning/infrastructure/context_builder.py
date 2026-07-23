"""Decision Context Builder — assemble everything the committee needs (I/O here).

Keeps the engine and models pure by doing all the reads itself. For a token it:

    * loads the latest persisted feature vector from the Feature Store and
      normalises it through the Feature Catalog (never touches raw PostgreSQL);
    * reads the wallet-intelligence snapshot straight off the triggering event;
    * looks up the most recent security verdict for the token (best-effort — its
      absence degrades the security features to neutral, never an error).

The result is an immutable :class:`DecisionContext`. It builds context; it takes
no decision.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import desc, select

from hades.contexts.intelligence.domain.events import WalletIntelligenceComputed
from hades.contexts.learning.application.feature_catalog import FeatureNormalizer
from hades.contexts.learning.domain.models import DecisionContext
from hades.contexts.learning.domain.ports import FeatureView
from hades.shared_kernel.logging import get_logger
from hades.shared_kernel.persistence.database import Database
from hades.shared_kernel.persistence.models.security import SecurityAssessmentRecord

_logger = get_logger("committee.context_builder")


class DecisionContextBuilder:
    """Assembles the full decision context for a token from all upstream reads."""

    def __init__(
        self,
        feature_view: FeatureView,
        normalizer: FeatureNormalizer,
        database: Database | None = None,
    ) -> None:
        self._features = feature_view
        self._normalizer = normalizer
        self._db = database

    async def build(self, event: WalletIntelligenceComputed) -> DecisionContext | None:
        token = event.token
        feature_set = await self._features.latest(token)
        if feature_set is None:
            return None
        vector = self._normalizer.normalize(feature_set)
        snapshot = event.snapshot
        security = await self._security(str(token.mint))

        return DecisionContext(
            token=token,
            at=datetime.now(UTC),
            vector=vector,
            security_approved=security["approved"],
            security_score=security["score"],
            security_sub_scores=security["sub_scores"],
            smart_money_count=snapshot.smart_money_count,
            dumb_money_count=snapshot.dumb_money_count,
            smart_money_pct_supply=snapshot.smart_money_pct_supply,
            avg_wallet_trust=snapshot.avg_trust,
            avg_wallet_risk=snapshot.avg_risk,
            cluster_count=snapshot.cluster_count,
            largest_cluster_pct=snapshot.largest_cluster_pct,
            wallets_observed=snapshot.wallets_observed,
        )

    async def _security(self, mint: str) -> dict[str, object]:
        neutral: dict[str, object] = {"approved": True, "score": 50.0, "sub_scores": {}}
        if self._db is None:
            return neutral
        try:
            async with self._db.session() as session:
                row = await session.scalar(
                    select(SecurityAssessmentRecord)
                    .where(SecurityAssessmentRecord.mint == mint)
                    .order_by(desc(SecurityAssessmentRecord.analyzed_at))
                    .limit(1)
                )
        except Exception as exc:  # never fail the committee on a DB hiccup
            _logger.warning("security_lookup_failed", mint=mint, error=str(exc))
            return neutral
        if row is None:
            return neutral
        return {
            "approved": bool(row.approved),
            "score": float(row.score),
            "sub_scores": {k: float(v) for k, v in (row.sub_scores or {}).items()},
        }

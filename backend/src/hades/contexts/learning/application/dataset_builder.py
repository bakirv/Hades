"""Dataset Builder — assemble a labelled training set from the outcome ledger.

Reads the append-only :class:`OutcomeStore` (executed trades *and* rejected
opportunities, each already carrying its ROI/TP/SL labels) and packages a
versioned :class:`Dataset` the Training/Validation engines consume. The whole
point of drawing from the ledger — rather than only from executed trades — is the
spec's rule: the brain must learn from what it declined and from losses, not only
from wins.

It builds datasets automatically; it takes no decision. The feature columns come
from the Feature Catalog plus the injected context features, so training and
serving see the same schema.
"""

from __future__ import annotations

from datetime import UTC, datetime

from hades.contexts.learning.domain.models import Dataset, TrainingSample
from hades.contexts.learning.domain.ports import OutcomeStore
from hades.shared_kernel.domain.identifiers import new_id
from hades.shared_kernel.logging import get_logger

_logger = get_logger("committee.dataset")


class DatasetBuilder:
    """Turns the outcome ledger into a versioned, reproducible dataset."""

    def __init__(self, outcomes: OutcomeStore) -> None:
        self._outcomes = outcomes

    async def build(
        self, *, name: str = "committee", since_iso: str | None = None, limit: int = 100_000
    ) -> Dataset:
        samples = await self._outcomes.load(since_iso=since_iso, limit=limit)
        feature_names = self._feature_names(samples)
        dataset = Dataset(
            dataset_id=new_id(),
            name=name,
            created_at=datetime.now(UTC),
            samples=samples,
            feature_names=feature_names,
            from_iso=since_iso,
            to_iso=datetime.now(UTC).isoformat(),
        )
        _logger.info(
            "dataset_built",
            dataset_id=dataset.dataset_id,
            size=dataset.size,
            positives=round(dataset.positive_rate, 3),
            executed=dataset.executed_count,
            rejected=dataset.rejected_count,
        )
        return dataset

    @staticmethod
    def _feature_names(samples: tuple[TrainingSample, ...]) -> tuple[str, ...]:
        names: set[str] = set()
        for sample in samples:
            names.update(sample.features.keys())
        return tuple(sorted(names))

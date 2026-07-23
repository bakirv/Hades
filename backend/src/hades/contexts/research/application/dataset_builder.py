"""Dataset Builder — turns copied history into train/validation/forward splits.

Pulls point-in-time samples (feature vector + realised forward-return label) from
the read-only :class:`HistoricalDataReader` and slices them chronologically so the
walk-forward invariant holds: validation and forward sets are always *later* than
training, never shuffled across the time boundary. Splitting by time (not at
random) is what makes the lab's out-of-sample claims honest.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from hades.contexts.research.domain.ports import HistoricalDataReader, HistoricalSample


@dataclass(frozen=True)
class DatasetSplit:
    """A chronological three-way split of samples."""

    train: tuple[HistoricalSample, ...]
    validation: tuple[HistoricalSample, ...]
    forward: tuple[HistoricalSample, ...]

    @property
    def total(self) -> int:
        return len(self.train) + len(self.validation) + len(self.forward)


class DatasetBuilder:
    """Loads and chronologically splits historical samples for the lab."""

    def __init__(self, reader: HistoricalDataReader) -> None:
        self._reader = reader

    async def load(
        self,
        *,
        from_iso: str | None = None,
        to_iso: str | None = None,
        limit: int = 100_000,
    ) -> tuple[HistoricalSample, ...]:
        samples = await self._reader.load_samples(from_iso=from_iso, to_iso=to_iso, limit=limit)
        return tuple(samples)

    def split(
        self,
        samples: Sequence[HistoricalSample],
        *,
        train_frac: float = 0.6,
        validation_frac: float = 0.2,
    ) -> DatasetSplit:
        n = len(samples)
        train_end = int(n * train_frac)
        val_end = int(n * (train_frac + validation_frac))
        return DatasetSplit(
            train=tuple(samples[:train_end]),
            validation=tuple(samples[train_end:val_end]),
            forward=tuple(samples[val_end:]),
        )

    async def build_split(
        self,
        *,
        from_iso: str | None = None,
        to_iso: str | None = None,
        train_frac: float = 0.6,
        validation_frac: float = 0.2,
    ) -> DatasetSplit:
        samples = await self.load(from_iso=from_iso, to_iso=to_iso)
        return self.split(samples, train_frac=train_frac, validation_frac=validation_frac)

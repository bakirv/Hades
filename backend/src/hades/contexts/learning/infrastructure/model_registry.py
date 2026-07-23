"""Model Registry adapters — the append-only, versioned home of every model.

In-memory and PostgreSQL implementations of the :class:`ModelRegistry` port.
Both enforce the same invariants: registering never overwrites an existing
``(name, version)``; promotion is exclusive (at most one ``PROMOTED`` version per
name) and archives the incumbent; nothing is ever deleted. Because every model
is a transparent weight set, the registry stores plain JSON — no opaque blobs.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from hades.contexts.learning.domain.models import ModelCard, ModelStatus
from hades.contexts.learning.infrastructure import serializers as ser
from hades.shared_kernel.logging import get_logger
from hades.shared_kernel.persistence.database import Database
from hades.shared_kernel.persistence.models.learning import CommitteeModelRecord

_logger = get_logger("committee.registry.store")


def _next_version(existing: tuple[str, ...]) -> str:
    highest = 0
    for version in existing:
        try:
            highest = max(highest, int(version))
        except ValueError:
            continue
    return str(highest + 1)


class InMemoryModelRegistry:
    """In-process registry for tests / single-process runs."""

    def __init__(self) -> None:
        self._by_id: dict[str, ModelCard] = {}

    async def register(self, card: ModelCard) -> None:
        for existing in self._by_id.values():
            if existing.name == card.name and existing.version == card.version:
                raise ValueError(f"model {card.name} v{card.version} already registered")
        self._by_id[card.model_id] = card

    async def get(self, model_id: str) -> ModelCard | None:
        return self._by_id.get(model_id)

    async def active(self, name: str) -> ModelCard | None:
        for card in self._by_id.values():
            if card.name == name and card.status is ModelStatus.PROMOTED:
                return card
        return None

    async def versions(self, name: str) -> tuple[ModelCard, ...]:
        return tuple(c for c in self._by_id.values() if c.name == name)

    async def list_active(self) -> tuple[ModelCard, ...]:
        return tuple(c for c in self._by_id.values() if c.status is ModelStatus.PROMOTED)

    async def next_version(self, name: str) -> str:
        return _next_version(tuple(c.version for c in self._by_id.values() if c.name == name))

    async def promote(self, model_id: str) -> ModelCard | None:
        card = self._by_id.get(model_id)
        if card is None:
            return None
        for other in self._by_id.values():
            if other.name == card.name and other.status is ModelStatus.PROMOTED:
                self._by_id[other.model_id] = other.model_copy(
                    update={"status": ModelStatus.ARCHIVED}
                )
        promoted = card.model_copy(
            update={"status": ModelStatus.PROMOTED, "promoted_at": datetime.now(UTC)}
        )
        self._by_id[model_id] = promoted
        return promoted

    async def set_status(self, model_id: str, status: str) -> None:
        card = self._by_id.get(model_id)
        if card is not None:
            self._by_id[model_id] = card.model_copy(update={"status": ModelStatus(status)})


class PostgresModelRegistry:
    """Durable registry backed by the ``committee_models`` table."""

    def __init__(self, database: Database) -> None:
        self._db = database

    async def register(self, card: ModelCard) -> None:
        row = ser.card_to_row(card)
        async with self._db.session() as session:
            session.add(CommitteeModelRecord(**row))

    async def get(self, model_id: str) -> ModelCard | None:
        async with self._db.session() as session:
            record = await session.scalar(
                select(CommitteeModelRecord).where(CommitteeModelRecord.model_id == model_id)
            )
        return self._to_card(record)

    async def active(self, name: str) -> ModelCard | None:
        async with self._db.session() as session:
            record = await session.scalar(
                select(CommitteeModelRecord).where(
                    CommitteeModelRecord.name == name,
                    CommitteeModelRecord.status == ModelStatus.PROMOTED.value,
                )
            )
        return self._to_card(record)

    async def versions(self, name: str) -> tuple[ModelCard, ...]:
        async with self._db.session() as session:
            records = (
                await session.scalars(
                    select(CommitteeModelRecord).where(CommitteeModelRecord.name == name)
                )
            ).all()
        return tuple(c for c in (self._to_card(r) for r in records) if c is not None)

    async def list_active(self) -> tuple[ModelCard, ...]:
        async with self._db.session() as session:
            records = (
                await session.scalars(
                    select(CommitteeModelRecord).where(
                        CommitteeModelRecord.status == ModelStatus.PROMOTED.value
                    )
                )
            ).all()
        return tuple(c for c in (self._to_card(r) for r in records) if c is not None)

    async def next_version(self, name: str) -> str:
        async with self._db.session() as session:
            records = (
                await session.scalars(
                    select(CommitteeModelRecord.version).where(CommitteeModelRecord.name == name)
                )
            ).all()
        return _next_version(tuple(records))

    async def promote(self, model_id: str) -> ModelCard | None:
        async with self._db.session() as session:
            target = await session.scalar(
                select(CommitteeModelRecord).where(CommitteeModelRecord.model_id == model_id)
            )
            if target is None:
                return None
            incumbents = (
                await session.scalars(
                    select(CommitteeModelRecord).where(
                        CommitteeModelRecord.name == target.name,
                        CommitteeModelRecord.status == ModelStatus.PROMOTED.value,
                    )
                )
            ).all()
            for incumbent in incumbents:
                incumbent.status = ModelStatus.ARCHIVED.value
            target.status = ModelStatus.PROMOTED.value
            target.promoted_at = datetime.now(UTC)
            return self._to_card(target)

    async def set_status(self, model_id: str, status: str) -> None:
        async with self._db.session() as session:
            record = await session.scalar(
                select(CommitteeModelRecord).where(CommitteeModelRecord.model_id == model_id)
            )
            if record is not None:
                record.status = status

    @staticmethod
    def _to_card(record: CommitteeModelRecord | None) -> ModelCard | None:
        if record is None:
            return None
        return ser.card_from_row(
            {
                "model_id": record.model_id,
                "name": record.name,
                "version": record.version,
                "kind": record.kind,
                "status": record.status,
                "dataset_id": record.dataset_id,
                "feature_names": record.feature_names,
                "weights": record.weights,
                "metrics": record.metrics,
                "trained_on_samples": record.trained_on_samples,
                "notes": record.notes,
                "created_at": record.created_at,
                "promoted_at": record.promoted_at,
            }
        )

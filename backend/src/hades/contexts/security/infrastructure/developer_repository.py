"""Developer reputation store adapters — PostgreSQL + in-memory.

The deployer track record Hades accumulates over time. ``observe_token`` is an
idempotent upsert that grows the created-token count; ``record_outcome`` folds in
a resolved result (rug / survived / success) as the platform learns how a
deployer's tokens ended. A blacklist hit on the deployer flips
``is_known_scammer``.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hades.contexts.common.domain.value_objects import WalletAddress
from hades.contexts.security.domain.models import DeveloperReputation as DeveloperReputationVO
from hades.shared_kernel.logging import get_logger
from hades.shared_kernel.persistence.database import Database
from hades.shared_kernel.persistence.models import DeveloperReputation as DevRow

_logger = get_logger("security.developer")


class PostgresDeveloperReputationStore:
    """PostgreSQL-backed deployer reputation."""

    def __init__(self, database: Database) -> None:
        self._db = database

    async def get(self, deployer: WalletAddress) -> DeveloperReputationVO | None:
        async with self._db.session() as session:
            row = await session.scalar(select(DevRow).where(DevRow.deployer == str(deployer)))
            if row is None:
                return None
            return _to_vo(row)

    async def observe_token(self, deployer: WalletAddress, *, mint: str) -> None:
        addr = str(deployer)
        stmt = (
            pg_insert(DevRow)
            .values(deployer=addr, tokens_created=1)
            .on_conflict_do_update(
                index_elements=[DevRow.deployer],
                set_={"tokens_created": DevRow.tokens_created + 1},
            )
        )
        async with self._db.session() as session:
            await session.execute(stmt)

    async def record_outcome(self, deployer: WalletAddress, *, outcome: str) -> None:
        column = {"rug": "rugs", "survived": "survived", "success": "successes"}.get(outcome)
        if column is None:
            _logger.warning("unknown_developer_outcome", outcome=outcome)
            return
        async with self._db.session() as session:
            row = await session.scalar(select(DevRow).where(DevRow.deployer == str(deployer)))
            if row is None:
                row = DevRow(deployer=str(deployer))
                session.add(row)
            setattr(row, column, getattr(row, column) + 1)


def _to_vo(row: DevRow) -> DeveloperReputationVO:
    return DeveloperReputationVO(
        deployer=row.deployer,
        tokens_created=row.tokens_created,
        rugs=row.rugs,
        survived=row.survived,
        successes=row.successes,
        avg_lifetime_hours=row.avg_lifetime_hours,
        avg_roi=row.avg_roi,
        is_known_scammer=row.is_known_scammer,
    )


class InMemoryDeveloperReputationStore:
    """In-process deployer reputation for tests."""

    def __init__(self, seed: dict[str, DeveloperReputationVO] | None = None) -> None:
        self.reputations: dict[str, DeveloperReputationVO] = dict(seed or {})

    async def get(self, deployer: WalletAddress) -> DeveloperReputationVO | None:
        return self.reputations.get(str(deployer))

    async def observe_token(self, deployer: WalletAddress, *, mint: str) -> None:
        addr = str(deployer)
        current = self.reputations.get(addr)
        if current is None:
            self.reputations[addr] = DeveloperReputationVO(deployer=addr, tokens_created=1)
        else:
            self.reputations[addr] = current.model_copy(
                update={"tokens_created": current.tokens_created + 1}
            )

    async def record_outcome(self, deployer: WalletAddress, *, outcome: str) -> None:
        addr = str(deployer)
        current = self.reputations.get(addr) or DeveloperReputationVO(deployer=addr)
        field = {"rug": "rugs", "survived": "survived", "success": "successes"}.get(outcome)
        if field is None:
            return
        self.reputations[addr] = current.model_copy(update={field: getattr(current, field) + 1})

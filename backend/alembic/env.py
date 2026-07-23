"""Alembic migration environment (async).

The database URL comes from Hades settings (env-driven) — never hardcoded here.
Model metadata is imported from the shared persistence ``Base`` so autogenerate
sees every ORM-mapped table across contexts once they are declared.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool

# Importing the models package registers every table on ``Base.metadata`` so
# autogenerate sees the full schema.
import hades.shared_kernel.persistence.models  # noqa: F401
from hades.shared_kernel.config import get_settings
from hades.shared_kernel.persistence.database import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Inject the runtime DSN.
_settings = get_settings()
config.set_main_option("sqlalchemy.url", _settings.postgres.dsn())

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: object) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)  # type: ignore[arg-type]
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())

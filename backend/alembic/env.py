from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.ext.asyncio import async_engine_from_config

from backend.db.base import get_database_url
from backend.shared.db import Base
from backend import models as _models  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", get_database_url())

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def _ensure_wide_version_table(connection) -> None:
    """Alembic stores the revision id in alembic_version.version_num, which it
    creates as VARCHAR(32). Revision 0008_pit_fundamentals_release_metadata is
    38 characters. SQLite ignores declared lengths, so this never surfaces
    there; Postgres enforces them and fails the UPDATE with
    StringDataRightTruncationError, leaving migrations permanently stuck.

    Create the table at a workable width before Alembic can create it narrow,
    and widen it if an earlier run already made it VARCHAR(32). Both statements
    are idempotent.
    """
    if connection.dialect.name != "postgresql":
        return
    connection.execute(
        text(
            "CREATE TABLE IF NOT EXISTS alembic_version ("
            "version_num VARCHAR(128) NOT NULL, "
            "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
        )
    )
    connection.execute(
        text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)")
    )


def do_run_migrations(connection) -> None:
    _ensure_wide_version_table(connection)
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
        # SQLAlchemy 2.0 connections are commit-as-you-go: closing one without
        # committing rolls it back. Without this, every migration and every
        # alembic_version row is discarded the moment this block exits, so the
        # next start finds an empty version table and replays from base.
        await connection.commit()

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    import asyncio

    asyncio.run(run_migrations_online())

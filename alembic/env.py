"""
Alembic environment — async-aware, configured to ignore Prisma-owned tables.

The shared Neon DB has a Prisma-owned half (User, Role, App, etc. —
managed from the Node side) and a Python-owned half (runs, decisions,
agent_reports — managed here). Alembic only sees the Python-owned half
via the `include_name` filter below, so autogenerate never tries to drop
or alter Prisma-owned tables.

URL resolution prefers `DIRECT_URL` (non-pooled) over `DATABASE_URL`
(pooled) — pooled connections from PgBouncer don't support the
session-level features Alembic needs (advisory locks, DDL transactions).
Falls back to DATABASE_URL only if DIRECT_URL is unset.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import settings
from app.db import Base, asyncpg_url
# Import models so they register with Base.metadata. New model files added
# in this directory must be imported here too — autogenerate is blind to
# uninstalled modules.
from app import models  # noqa: F401


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


# Resolve the URL once. DIRECT_URL preferred (non-pooled); fall back to
# DATABASE_URL when not set (e.g., local dev without a pooler).
raw_url = settings.DIRECT_URL or settings.DATABASE_URL
url, connect_args = asyncpg_url(raw_url)


def include_name(name: str, type_: str, parent_names: dict) -> bool:
    """
    Tell Alembic which DB objects to track. Other tables (Prisma-owned)
    stay invisible — autogenerate never tries to drop them.

    Add new Python-owned table names here when models grow.
    """
    if type_ == "table":
        return name in {"runs", "decisions", "agent_reports"}
    # Indexes, FKs, etc. on tracked tables — always include.
    return True


def run_migrations_offline() -> None:
    """Generate SQL without connecting to the DB. Mostly used by CI dry-runs."""
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Async runner — opens a connection via asyncpg, runs migrations, closes."""
    cfg = config.get_section(config.config_ini_section) or {}
    cfg["sqlalchemy.url"] = url
    connectable = async_engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

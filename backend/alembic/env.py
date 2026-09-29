"""P4 — PostgreSQL + Alembic Production Database Foundation.

This is the async template (`alembic init -t async`), not the default
sync one — deliberately, since the application itself is async
SQLAlchemy end to end (app/db/session.py) and this keeps migrations
using the exact same driver (asyncpg) the app uses at runtime, rather
than adding a second database driver dependency (psycopg2/psycopg)
that would exist for migrations alone. `connection.run_sync(...)` is
what lets Alembic's fundamentally-synchronous migration-running
machinery execute over that async connection — this file's only real
addition on top of the stock async template is wiring in the app's own
settings/metadata instead of the template's placeholders.

`target_metadata` is the application's own `Base.metadata` — every
model already registered by `import app.models` (the same aggregator
module app/main.py and every test file already import from). Nothing
here duplicates a model definition; autogenerate diffs against the
real, current model layer.

The database URL is read from the application's own
`get_settings().database_url` (which itself already resolves from
`DATABASE_URL` in the environment — see app/core/config.py) rather than
a URL written into alembic.ini. There is exactly one place a
connection string is configured for this whole project, both for the
running app and for migrations, and environment variables are it — see
this file's `_get_database_url` for the one narrow exception (the
`asyncpg`->`psycopg` driver swap explained there).

Alembic is Postgres-only in this project by design (see the P4 report's
"schema.sql decision" and "Development behavior" sections): SQLite is
tests/ephemeral-dev-only and is never a migration target. Running
`alembic upgrade`/`revision --autogenerate` against a `sqlite://` URL
fails loudly below rather than silently producing a migration that
would drift from what Postgres actually needs.
"""

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Makes `app.*` importable regardless of the CWD alembic is invoked
# from — this file lives at backend/alembic/env.py, so backend/ (one
# level up from this file's own directory) is the app package's root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402
import app.models  # noqa: E402,F401  (registers every model on Base.metadata)

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _get_database_url() -> str:
    url = get_settings().database_url
    if "sqlite" in url:
        raise RuntimeError(
            "Alembic targets PostgreSQL only in this project — SQLite is "
            "tests/ephemeral-dev-only and is never migrated (see this "
            "file's module docstring). Set DATABASE_URL to a "
            "postgresql+asyncpg://... connection string before running "
            "alembic."
        )
    # asyncpg is what the application itself uses (app/db/session.py) —
    # reused here unchanged so migrations and the running app share one
    # driver. SQLAlchemy's sync `pool`/autogenerate machinery still
    # drives this through `connection.run_sync(...)` below; the
    # connection itself is genuinely async.
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emits SQL without a live DB
    connection. Not this project's normal path (see the P4 report), but
    kept working: useful for generating a reviewable SQL script."""
    url = _get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Creates an async Engine from the application's own DATABASE_URL
    and associates a connection with the migration context — the async
    counterpart of the sync template's `run_migrations_online`."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _get_database_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

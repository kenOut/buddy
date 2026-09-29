"""P2.1 — Test Database Isolation Fix.

The engine and session factory here are resolved lazily, keyed by the
*current* database URL, rather than built once at module-import time.

Why: this module, like every module, is only ever truly imported once
per Python process — and `get_settings()` is `@lru_cache`d on top of
that. Building `engine`/`AsyncSessionLocal` as plain module-level
objects (the previous shape) meant they were permanently fixed to
whichever `DATABASE_URL` happened to be active the first time *any*
code anywhere imported this module. This project's test files each set
`os.environ["DATABASE_URL"]` before importing `app.main`, expecting an
isolated SQLite file per file — which genuinely works when a file runs
alone, but silently broke down for every file after the first when the
full suite ran in one pytest process: they all ended up sharing
whichever database the first-imported test file configured, since
nothing ever re-read the environment after that first import.

Production is unaffected by any of this: `DATABASE_URL` is set once,
in the environment, before the process starts, and never changes for
the life of that process — so `_current_database_url()` always
resolves to the same value there, `get_engine()`/`get_session_factory()`
build their engine/sessionmaker exactly once (same as before), and
nothing about connection pooling, transaction semantics, or request
behavior changes. This only starts mattering when `DATABASE_URL`
legitimately changes within a single process, which today only happens
in this test suite's own established convention.

`get_settings()` itself keeps its `@lru_cache` — untouched, and still
governs every other setting normally, in production exactly as before.
Only the database URL is read directly from the environment here
(falling back to the cached settings' value when unset), because it is
the one setting this project's own tests deliberately vary per file.
"""

import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

_engines: dict[str, AsyncEngine] = {}
_session_factories: dict[str, async_sessionmaker[AsyncSession]] = {}


def _current_database_url() -> str:
    return os.environ.get("DATABASE_URL") or get_settings().database_url


def is_sqlite_database() -> bool:
    """P4 — PostgreSQL + Alembic Production Database Foundation. The one
    place app/main.py's lifespan decides whether it's safe to call
    `Base.metadata.create_all(...)`: true for tests and local SQLite
    dev, false for anything else (local Postgres dev or production),
    which is expected to already be migrated via `alembic upgrade head`
    run as a separate step — see alembic/env.py's own module docstring
    for why Alembic itself refuses to target a `sqlite://` URL at all."""
    return "sqlite" in _current_database_url()


def get_engine() -> AsyncEngine:
    """Returns the engine for the *current* database URL, building and
    caching it on first use for that URL. A process that only ever sees
    one URL (production, or any single test file run alone) builds
    exactly one engine, exactly as the previous module-level version
    did."""
    url = _current_database_url()
    engine = _engines.get(url)
    if engine is None:
        connect_args = {"check_same_thread": False} if "sqlite" in url else {}
        engine = create_async_engine(url, echo=False, connect_args=connect_args)
        _engines[url] = engine
    return engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    url = _current_database_url()
    factory = _session_factories.get(url)
    if factory is None:
        factory = async_sessionmaker(get_engine(), expire_on_commit=False, class_=AsyncSession)
        _session_factories[url] = factory
    return factory


class _DynamicSessionLocal:
    """A drop-in stand-in for `async_sessionmaker(engine)`: calling it
    returns a new `AsyncSession`, exactly like before. The difference is
    entirely internal — each call resolves the *current* URL's session
    factory rather than one bound forever to whatever URL was active at
    import time. Every existing `from app.db.session import
    AsyncSessionLocal` / `AsyncSessionLocal()` call site (there are many,
    across services and tests) keeps working completely unchanged."""

    def __call__(self) -> AsyncSession:
        return get_session_factory()()


AsyncSessionLocal = _DynamicSessionLocal()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session

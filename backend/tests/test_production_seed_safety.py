"""P4.1 — Production Seed Safety Hardening.

Proves the actual `app.main.lifespan` function behaves correctly in
both environments — not a reimplementation of its logic, the real
function, run directly as an async context manager against a fresh,
empty, isolated SQLite database, with `app.main`'s own module-level
`settings` monkeypatched to a production-configured Settings instance
for the production case (restored immediately after). This is the only
way to exercise the production branch: `app.main` is imported once per
process, and its `settings` variable is captured at that import moment,
exactly like every other module-level object this project's P2.1 fix
had to account for.

Each test uses its own uniquely-named SQLite file and re-asserts
`os.environ["DATABASE_URL"]` immediately before calling `lifespan()` —
not just once at module import time. This project's test files
conventionally set `DATABASE_URL` once at the top of the file, relying
on `app.db.session`'s P2.1 lazy, URL-keyed engine resolution to read it
correctly later; that convention alone was not reliable enough here; in
a full-suite run this file's own tests intermittently observed a
different `DATABASE_URL` than the one set at this file's own import
time by the time a later test function actually executed. Setting it
again at the point of use removes any dependency on exactly when this
module's top-level code ran relative to every other collected test
file's own `os.environ` reassignment — the same defensive lesson P3's
test_provisioning.py identity-collision fix already established for a
different kind of process-wide shared state.

Section 6's Postgres-specific empty-database check is covered
separately by scripts/verify_postgres.py, not here — that script needs
a real Postgres instance this file's own SQLite-only convention
deliberately avoids depending on.
"""

import asyncio
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, select

import app.main as app_main
from app.core.config import Settings
from app.db.session import AsyncSessionLocal
from app.models import Capability, Employee, Organization


def run(coro):
    return asyncio.run(coro)


def _fresh_db_url() -> str:
    """A brand-new, uniquely-named SQLite file for exactly one test —
    set as the active DATABASE_URL immediately, and cleaned up by the
    caller. Guarantees this test can never observe another test's
    (in this file or any other) leftover state."""
    path = Path(__file__).resolve().parent.parent / f"test_production_seed_safety_{uuid.uuid4().hex}.db"
    path.unlink(missing_ok=True)
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{path}"
    return path


async def _counts() -> tuple[int, int, int]:
    async with AsyncSessionLocal() as db:
        org_count = (await db.execute(select(func.count()).select_from(Organization))).scalar_one()
        employee_count = (await db.execute(select(func.count()).select_from(Employee))).scalar_one()
        capability_count = (await db.execute(select(func.count()).select_from(Capability))).scalar_one()
    return org_count, employee_count, capability_count


def test_development_environment_seeds_demo_data():
    """The actual lifespan function, run for real, against a fresh
    empty database, with the default (development) environment —
    proves seed_demo_data remains available and unchanged for
    development, not just "the code path wasn't deleted"."""
    db_path = _fresh_db_url()
    try:
        async def _scenario():
            async with app_main.lifespan(app_main.app):
                pass
            return await _counts()

        org_count, employee_count, capability_count = run(_scenario())
    finally:
        db_path.unlink(missing_ok=True)

    assert org_count > 0, "development startup must seed the demo organization"
    assert employee_count > 0, "development startup must seed demo employees"
    assert capability_count > 0, "capabilities must be seeded in development too"


def test_production_environment_does_not_seed_demo_data():
    """The core P4.1 guarantee, proven against the real lifespan
    function: with environment=production, zero demo organizations and
    zero demo employees exist after startup — capabilities still do
    (see the next test), proving this isn't just "nothing happened" but
    specifically "demo content was skipped, foundational reference data
    was not"."""
    db_path = _fresh_db_url()
    original_settings = app_main.settings
    app_main.settings = Settings(
        environment="production",
        provisioning_api_key="test-production-key",
        app_base_url="https://buddy.kowri.example",
        admin_password="test-production-admin-password",
        admin_session_secret="test-production-admin-session-secret",
        employee_session_secret="test-production-employee-session-secret",
        invitation_token_secret="test-production-invitation-token-secret",
        cors_origins="https://buddy.kowri.example",
    )
    try:
        async def _scenario():
            async with app_main.lifespan(app_main.app):
                pass
            return await _counts()

        org_count, employee_count, _capability_count = run(_scenario())
    finally:
        app_main.settings = original_settings
        db_path.unlink(missing_ok=True)

    assert org_count == 0, "production startup must never seed a demo organization"
    assert employee_count == 0, "production startup must never seed demo employees"


def test_production_environment_still_seeds_capabilities():
    """The explicit distinction P4.1 asked for: capability seeding is
    NOT demo content (every Quest/Mission capability mapping and every
    CapabilityEvidence/CapabilityProfile row FKs into it, in every
    environment) — it must still run in production, unlike
    seed_demo_data."""
    db_path = _fresh_db_url()
    original_settings = app_main.settings
    app_main.settings = Settings(
        environment="production",
        provisioning_api_key="test-production-key",
        app_base_url="https://buddy.kowri.example",
        admin_password="test-production-admin-password",
        admin_session_secret="test-production-admin-session-secret",
        employee_session_secret="test-production-employee-session-secret",
        invitation_token_secret="test-production-invitation-token-secret",
        cors_origins="https://buddy.kowri.example",
    )
    try:
        async def _scenario():
            async with app_main.lifespan(app_main.app):
                pass
            return await _counts()

        _org_count, _employee_count, capability_count = run(_scenario())
    finally:
        app_main.settings = original_settings
        db_path.unlink(missing_ok=True)

    assert capability_count > 0, "capability seeding must remain unconditional, including in production"


def test_production_startup_never_adds_to_an_already_seeded_database():
    """A stronger claim than "the org table ends up empty on a fresh
    database": given a database that already has organizations in it
    from a PRIOR (development) run, a SUBSEQUENT production startup
    against that SAME database must not add any more (and must not
    error either) — production skips the demo-seeding block entirely,
    it doesn't rely on the "does one already exist" guard query to
    correctly no-op."""
    db_path = _fresh_db_url()
    original_settings = app_main.settings
    try:
        async def _seed_as_development():
            async with app_main.lifespan(app_main.app):
                pass

        run(_seed_as_development())
        org_count_after_dev, _, _ = run(_counts())
        assert org_count_after_dev > 0

        os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
        app_main.settings = Settings(
            environment="production",
            provisioning_api_key="test-production-key",
            app_base_url="https://buddy.kowri.example",
            admin_password="test-production-admin-password",
            admin_session_secret="test-production-admin-session-secret",
            employee_session_secret="test-production-employee-session-secret",
            invitation_token_secret="test-production-invitation-token-secret",
            cors_origins="https://buddy.kowri.example",
        )

        async def _scenario():
            async with app_main.lifespan(app_main.app):
                pass
            return await _counts()

        org_count_after_prod, _, _ = run(_scenario())
    finally:
        app_main.settings = original_settings
        db_path.unlink(missing_ok=True)

    assert org_count_after_prod == org_count_after_dev, (
        "a production startup against an already-seeded database must not add or "
        "otherwise touch organizations"
    )


@pytest.fixture(autouse=True)
def _restore_database_url_after_each_test():
    """This file deliberately mutates `os.environ["DATABASE_URL"]`
    per-test rather than once at import time (see module docstring) —
    restores whatever was active before this file's tests ran, so as
    not to leave a stale value for any test collected after this file."""
    original = os.environ.get("DATABASE_URL")
    yield
    if original is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = original

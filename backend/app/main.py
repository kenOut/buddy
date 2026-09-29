import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import AsyncSessionLocal, get_engine, is_sqlite_database
from app.models import Organization
from app.seed.capabilities import ensure_capabilities_seeded
from app.seed.seed_data import seed_demo_data

settings = get_settings()

# P3 — Email Provider Foundation. This project had no structured
# logging configuration at all before this (see the P0 architecture
# audit) — email_service.py's own safe, non-secret log lines
# (email_type/employee_id/provider/accepted, never a token or email
# body) are the first thing that needs one. A plain INFO-level
# StreamHandler on the root logger is the smallest fix that makes those
# lines actually visible rather than silently dropped by Python
# logging's default WARNING threshold; nothing else in the app depends
# on this beyond that.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # P4 — PostgreSQL + Alembic Production Database Foundation.
    # `Base.metadata.create_all(...)` only ever runs against SQLite —
    # tests, and local SQLite dev — where it's a cheap, ephemeral,
    # test-only schema creation with no production authority. Any other
    # DATABASE_URL (local Postgres dev, or production) is expected to
    # already be migrated via `alembic upgrade head`, run as its own
    # separate deploy step (see backend/alembic/); the application
    # itself never mutates that schema. See is_sqlite_database's own
    # docstring, and the P4 report's "Application startup changes"
    # section, for the full reasoning.
    if is_sqlite_database():
        async with get_engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        # P4.1 — Production Seed Safety Hardening. `seed_demo_data`
        # writes a fake organization/department/employees (Michael
        # Mensah et al.) — genuine demo *content*, only ever appropriate
        # in development or a demo environment, never production. The
        # guard is the application's own `environment` setting
        # (P2.1/P3's existing fail-closed pattern for secrets, reused
        # here for a different kind of production hazard), not
        # `DATABASE_URL`/driver-based inference — a local Postgres dev
        # database must still get demo data, and nothing about which
        # driver is in use says anything about whether this process is
        # actually production. The whole block, including the
        # "does an Organization already exist" guard query, sits inside
        # this check: production never even runs the query, so there is
        # no code path in production that touches demo-seeding logic at
        # all, not just a state where it happens to no-op.
        if settings.environment != "production":
            result = await session.execute(select(Organization))
            if result.scalars().first() is None:
                await seed_demo_data(session)

        # Capabilities are a global reference table, not demo-org-scoped
        # — genuinely foundational, not demo *content*: every Quest/
        # Mission capability mapping and every CapabilityEvidence/
        # CapabilityProfile row has a foreign key into this table, in
        # every environment including production. Skipping it there
        # would leave a production deployment with a broken capability
        # system, not a safely-empty one — so this stays unconditional,
        # seeded idempotently on every startup regardless of
        # environment, unlike seed_demo_data above.
        await ensure_capabilities_seeded(session)

    yield


# P5 — Production Security Hardening. `/docs`, `/redoc`, and the raw
# `/openapi.json` schema are enabled by default (unchanged from every
# earlier phase) but disabled by default specifically in production —
# they don't leak secrets, but they do publish the full internal API
# surface (every endpoint, every schema field) to anyone who requests
# them, which a production deployment shouldn't do unprompted. Override
# either way with ENABLE_API_DOCS=true/false; see Settings.api_docs_enabled.
_docs_enabled = settings.api_docs_enabled
app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)

# P5 — Production Security Hardening. Rejects requests whose Host
# header doesn't match an explicitly configured value — a no-op by
# default (settings.trusted_hosts defaults to "*", i.e. accept any
# Host), so this never changes behavior unless TRUSTED_HOSTS is set.
# See Settings.trusted_hosts for why this stays opt-in rather than
# fail-closed like the secrets above.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_host_list)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class _MaxBodySizeMiddleware(BaseHTTPMiddleware):
    """P5 — Production Security Hardening. Rejects a request body over
    settings.max_request_body_bytes with 413, using the client-supplied
    Content-Length header as a cheap upfront check (a request that lies
    about its own Content-Length only hurts itself — the body is never
    read into memory here either way, so there's nothing for a mismatched
    header to exploit). A blunt backstop against obviously-abusive
    payloads reaching application/service logic at all, not a
    replacement for real per-field validation."""

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > settings.max_request_body_bytes:
                    return JSONResponse(status_code=413, content={"detail": "Request body too large"})
            except ValueError:
                pass
        return await call_next(request)


app.add_middleware(_MaxBodySizeMiddleware)

app.include_router(api_router, prefix=settings.api_v1_prefix)

# Employee avatar uploads (employees.upload_employee_avatar) — served back
# out from the same directory they're written to. Not API-versioned since
# it's plain file serving, not a JSON endpoint.
_STATIC_DIR = Path(__file__).resolve().parent / "static"
_STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/health")
async def health():
    return {"status": "ok"}

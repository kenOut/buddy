from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import AsyncSessionLocal, engine
from app.models import Organization
from app.seed.capabilities import ensure_capabilities_seeded
from app.seed.seed_data import seed_demo_data

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Organization))
        if result.scalars().first() is None:
            await seed_demo_data(session)

        # Capabilities are a global reference table, not demo-org-scoped —
        # seeded unconditionally (idempotently) on every startup.
        await ensure_capabilities_seeded(session)

    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/health")
async def health():
    return {"status": "ok"}

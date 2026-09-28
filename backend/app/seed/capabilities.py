"""Seeds the global Capability reference table.

Runs unconditionally (idempotently) at every startup, independent of the
demo org/employee seed gate in seed_data.py — capabilities aren't
organization-scoped demo data, they're a fixed taxonomy the rest of the
system refers to by stable key.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CAPABILITY_KEYS, Capability

CAPABILITY_DEFINITIONS: dict[str, dict[str, str]] = {
    "technical_understanding": {
        "name": "Technical Understanding",
        "description": "Understands how systems, services, and tools work together.",
    },
    "troubleshooting": {
        "name": "Troubleshooting",
        "description": "Diagnoses problems by following evidence to a root cause.",
    },
    "problem_solving": {
        "name": "Problem Solving",
        "description": "Reasons through ambiguous situations to a sound conclusion.",
    },
    "documentation": {
        "name": "Documentation",
        "description": "Explains findings and decisions clearly enough for others to follow.",
    },
    "communication": {
        "name": "Communication",
        "description": "Shares information in a way that's clear, structured, and easy to act on.",
    },
    "independence": {
        "name": "Independence",
        "description": "Makes progress and sound decisions without needing close supervision.",
    },
}


async def ensure_capabilities_seeded(db: AsyncSession) -> None:
    result = await db.execute(select(Capability.key))
    existing_keys = set(result.scalars().all())

    created = False
    for key in CAPABILITY_KEYS:
        if key in existing_keys:
            continue
        definition = CAPABILITY_DEFINITIONS[key]
        db.add(Capability(key=key, name=definition["name"], description=definition["description"]))
        created = True

    if created:
        await db.commit()

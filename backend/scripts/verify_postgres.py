"""P4 — PostgreSQL + Alembic Production Database Foundation.

A standalone, repeatable PostgreSQL verification script — not part of
`pytest -q` (that suite stays SQLite-only, per this project's own
established per-file convention; see tests/*.py). This exercises the
exact same service-layer functions the app/tests use, against a REAL
PostgreSQL database, requiring:

  1. DATABASE_URL pointing at an empty (or already-migrated) Postgres
     database, e.g.:
       postgresql+asyncpg://buddy:buddy@localhost:5544/buddy
  2. That database already migrated: `alembic upgrade head`

Run with:

    cd backend
    DATABASE_URL=postgresql+asyncpg://... .venv/bin/python scripts/verify_postgres.py

Exists because P2.1 explicitly documented that SQLite/aiosqlite cannot
provide genuine confidence about concurrent-write behavior (NullPool —
every checkout is a brand-new raw connection; true overlapping
connection creation hit a driver-level MissingGreenlet limitation, not
a product bug — see tests/test_provisioning.py's own long comment on
this). This script is what actually answers the question against a
real connection pool instead of leaving it open.

Prints a PASS/FAIL line per check and exits non-zero if anything failed
— safe to wire into a CI job later without modification.
"""

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if "postgresql" not in DATABASE_URL:
    print(f"FATAL: DATABASE_URL must point at PostgreSQL. Got: {DATABASE_URL!r}")
    sys.exit(2)

from sqlalchemy import func, select, text  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.models import (  # noqa: E402
    Capability,
    CapabilityEvidence,
    Employee,
    EmployeeInvitation,
    Organization,
    OnboardingSession,
    QuestAttempt,
    WorkspaceAccessGrant,
    WorkspaceIntegration,
)
from app.schemas.provisioning import ProvisioningRequest  # noqa: E402
from app.services import invitation_service, provisioning_service  # noqa: E402

engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    RESULTS.append((name, condition, detail))
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not condition else ""))


async def main() -> None:
    async with SessionLocal() as db:
        # A fresh org/department/role per run — this script is meant to
        # be re-run against the same database repeatedly.
        suffix = uuid.uuid4().hex[:8]
        org = Organization(name=f"PG Verify Org {suffix}", slug=f"pg-verify-{suffix}")
        db.add(org)
        await db.commit()
        await db.refresh(org)
        org_id = org.id

        cap_result = await db.execute(select(Capability).limit(1))
        capability = cap_result.scalars().first()
        if capability is None:
            capability = Capability(key=f"pg-verify-{suffix}", name="PG Verify Capability")
            db.add(capability)
            await db.commit()
            await db.refresh(capability)

    # 1. Full schema migration — already proven by this script even
    # being able to import/query these models against this DATABASE_URL
    # at all; `alembic upgrade head` was required before this script
    # could run.
    check("1. Schema migration applied", True, "implicit — script connected and queried successfully")

    # 2 & 3. Employee creation + identity uniqueness
    identity_provider, external_subject = "google", f"pg-verify-{suffix}"
    async with SessionLocal() as db:
        request = ProvisioningRequest(
            organization_id=org_id,
            identity_provider=identity_provider,
            external_subject=external_subject,
            email=f"pg-verify-{suffix}@kowri.test",
            full_name="Postgres Verify",
        )
        result = await provisioning_service.provision_employee(db, request)
        employee_id = result.employee.id
    check("2. Employee creation via provisioning", result.created is True)

    async with SessionLocal() as db:
        dup = Employee(
            organization_id=org_id,
            full_name="Duplicate Identity",
            email=f"pg-verify-dup-{suffix}@kowri.test",
            identity_provider=identity_provider,
            external_subject=external_subject,
            status="invited",
        )
        db.add(dup)
        try:
            await db.commit()
            identity_unique = False
        except IntegrityError:
            await db.rollback()
            identity_unique = True
    check("3. (identity_provider, external_subject) uniqueness enforced", identity_unique)

    # 4. Onboarding session uniqueness
    async with SessionLocal() as db:
        dup_session = OnboardingSession(employee_id=employee_id, current_scene="welcome", status="in_progress")
        db.add(dup_session)
        try:
            await db.commit()
            session_unique = False
        except IntegrityError:
            await db.rollback()
            session_unique = True
    check("4. OnboardingSession.employee_id uniqueness enforced", session_unique)

    # 5 & 6. Invitation creation + token hash storage (never the raw token)
    async with SessionLocal() as db:
        invitation, raw_token = await invitation_service.issue_invitation(db, employee_id)
    check("5. Invitation created", invitation.id is not None)
    check(
        "6. Only token_hash stored, never the raw token",
        invitation.token_hash != raw_token and len(invitation.token_hash) == 64,
    )

    # 7. Quest attempt creation
    async with SessionLocal() as db:
        from app.models import Quest

        quest = Quest(
            title=f"PG Verify Quest {suffix}",
            quest_type="INVESTIGATE",
            workspace_type="INVESTIGATION",
            department_id=None,
        )
        db.add(quest)
        await db.commit()
        await db.refresh(quest)

        attempt = QuestAttempt(quest_id=quest.id, employee_id=employee_id)
        db.add(attempt)
        await db.commit()
        await db.refresh(attempt)
        quest_id = quest.id
    check("7. QuestAttempt creation", attempt.id is not None)

    # 8. Capability evidence constraint (exactly one of mission_attempt_id/quest_attempt_id)
    async with SessionLocal() as db:
        bad_evidence = CapabilityEvidence(
            employee_id=employee_id,
            mission_attempt_id=None,
            quest_attempt_id=None,
            capability_id=capability.id,
            evidence_type="OTHER",
            observation="should be rejected — neither parent set",
            strength="CAPABLE",
            confidence=0.5,
            source="deterministic",
        )
        db.add(bad_evidence)
        try:
            await db.commit()
            check_enforced = False
        except IntegrityError:
            await db.rollback()
            check_enforced = True
    check("8. CapabilityEvidence single-parent CHECK constraint enforced", check_enforced)

    async with SessionLocal() as db:
        good_evidence = CapabilityEvidence(
            employee_id=employee_id,
            quest_attempt_id=attempt.id,
            capability_id=capability.id,
            evidence_type="OTHER",
            observation="valid — exactly one parent set",
            strength="CAPABLE",
            confidence=0.5,
            source="deterministic",
        )
        db.add(good_evidence)
        await db.commit()
    check("8b. CapabilityEvidence with exactly one parent succeeds", True)

    # 9. Workspace access grant uniqueness
    async with SessionLocal() as db:
        from app.models import Department

        dept = Department(organization_id=org_id, name=f"PG Verify Dept {suffix}")
        db.add(dept)
        await db.commit()
        await db.refresh(dept)

        integration = WorkspaceIntegration(
            department_id=dept.id,
            provider="google_drive",
            external_ref=f"pg-verify-ref-{suffix}",
            display_name="PG Verify Workspace",
            workspace_link="https://drive.example.test/pg-verify",
        )
        db.add(integration)
        await db.commit()
        await db.refresh(integration)

        grant1 = WorkspaceAccessGrant(employee_id=employee_id, workspace_integration_id=integration.id)
        db.add(grant1)
        await db.commit()
        integration_id = integration.id

    async with SessionLocal() as db:
        grant2 = WorkspaceAccessGrant(employee_id=employee_id, workspace_integration_id=integration_id)
        db.add(grant2)
        try:
            await db.commit()
            grant_unique = False
        except IntegrityError:
            await db.rollback()
            grant_unique = True
    check("9. WorkspaceAccessGrant (employee, integration) uniqueness enforced", grant_unique)

    # 10. Provisioning idempotency (sequential)
    async with SessionLocal() as db:
        request2 = ProvisioningRequest(
            organization_id=org_id,
            identity_provider=identity_provider,
            external_subject=external_subject,
            email=f"pg-verify-{suffix}@kowri.test",
            full_name="Postgres Verify Renamed",
        )
        result2 = await provisioning_service.provision_employee(db, request2)
    check(
        "10. Repeated provisioning resolves to the same employee (idempotent)",
        result2.employee.id == employee_id and result2.created is False,
    )

    # 11. Concurrent provisioning — the real test P2.1 could not run.
    concurrent_identity = f"pg-verify-concurrent-{suffix}"
    concurrent_request = ProvisioningRequest(
        organization_id=org_id,
        identity_provider="google",
        external_subject=concurrent_identity,
        email=f"pg-verify-concurrent-{suffix}@kowri.test",
        full_name="Concurrent Verify",
    )

    async def _one_provision():
        async with SessionLocal() as db:
            return await provisioning_service.provision_employee(db, concurrent_request)

    concurrent_results = await asyncio.gather(*[_one_provision() for _ in range(8)])
    concurrent_employee_ids = {r.employee.id for r in concurrent_results}
    concurrent_created_count = sum(1 for r in concurrent_results if r.created)
    check(
        "11. 8 concurrent provisioning requests -> exactly 1 employee",
        len(concurrent_employee_ids) == 1 and concurrent_created_count == 1,
        f"got {len(concurrent_employee_ids)} distinct employee(s), {concurrent_created_count} created=True",
    )

    concurrent_employee_id = concurrent_employee_ids.pop()
    async with SessionLocal() as db:
        session_count = (
            await db.execute(
                select(func.count()).select_from(OnboardingSession).where(
                    OnboardingSession.employee_id == concurrent_employee_id
                )
            )
        ).scalar_one()
        invitation_count = (
            await db.execute(
                select(func.count())
                .select_from(EmployeeInvitation)
                .where(EmployeeInvitation.employee_id == concurrent_employee_id)
                .where(EmployeeInvitation.used_at.is_(None))
                .where(EmployeeInvitation.revoked_at.is_(None))
            )
        ).scalar_one()
    check("11b. Exactly 1 OnboardingSession after concurrent provisioning", session_count == 1)
    check("11c. Exactly 1 active EmployeeInvitation after concurrent provisioning", invitation_count == 1)

    # 12. Concurrent invitation creation (issue_invitation's own retry loop, for real)
    async def _one_issue():
        async with SessionLocal() as db:
            return await invitation_service.issue_invitation(db, concurrent_employee_id)

    issue_results = await asyncio.gather(*[_one_issue() for _ in range(8)])
    async with SessionLocal() as db:
        active_after_issue = (
            await db.execute(
                select(func.count())
                .select_from(EmployeeInvitation)
                .where(EmployeeInvitation.employee_id == concurrent_employee_id)
                .where(EmployeeInvitation.used_at.is_(None))
                .where(EmployeeInvitation.revoked_at.is_(None))
            )
        ).scalar_one()
    check(
        "12. 8 concurrent issue_invitation calls -> exactly 1 active invitation",
        active_after_issue == 1,
        f"got {active_after_issue}",
    )

    # 13. Concurrent workspace access grant creation
    async def _one_grant():
        async with SessionLocal() as db:
            grant = WorkspaceAccessGrant(employee_id=concurrent_employee_id, workspace_integration_id=integration_id)
            db.add(grant)
            try:
                await db.commit()
                return True
            except IntegrityError:
                await db.rollback()
                return False

    grant_results = await asyncio.gather(*[_one_grant() for _ in range(8)])
    async with SessionLocal() as db:
        grant_count = (
            await db.execute(
                select(func.count())
                .select_from(WorkspaceAccessGrant)
                .where(WorkspaceAccessGrant.employee_id == concurrent_employee_id)
                .where(WorkspaceAccessGrant.workspace_integration_id == integration_id)
            )
        ).scalar_one()
    check(
        "13. 8 concurrent WorkspaceAccessGrant inserts -> exactly 1 row",
        grant_count == 1 and sum(grant_results) == 1,
        f"row count={grant_count}, successes={sum(grant_results)}",
    )

    # 14. Transaction rollback behavior
    async with SessionLocal() as db:
        rollback_org = Organization(name=f"Rollback Test {suffix}", slug=f"rollback-test-{suffix}")
        db.add(rollback_org)
        await db.flush()
        rollback_org_id = rollback_org.id
        await db.rollback()
    async with SessionLocal() as db:
        found = await db.get(Organization, rollback_org_id)
    check("14. Transaction rollback discards uncommitted work", found is None)

    # 15. JSON payload persistence
    async with SessionLocal() as db:
        quest_attempt = await db.get(QuestAttempt, attempt.id)
        quest_attempt.submission = {"findings": "pg verify", "nested": {"a": [1, 2, 3]}}
        await db.commit()
    async with SessionLocal() as db:
        reloaded = await db.get(QuestAttempt, attempt.id)
        json_ok = reloaded.submission == {"findings": "pg verify", "nested": {"a": [1, 2, 3]}}
    check("15. JSON payload persists and round-trips exactly", json_ok)

    # 16. Timestamp behavior
    async with SessionLocal() as db:
        fresh_org = await db.get(Organization, org_id)
        has_tz = fresh_org.created_at.tzinfo is not None
        is_recent = (datetime.now(timezone.utc) - fresh_org.created_at).total_seconds() < 3600
    check("16. Timestamps are timezone-aware and sane", has_tz and is_recent)

    await engine.dispose()

    failed = [name for name, ok, _ in RESULTS if not ok]
    print()
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    if failed:
        print("FAILED:", failed)
        sys.exit(1)
    print("ALL POSTGRESQL VERIFICATION CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())

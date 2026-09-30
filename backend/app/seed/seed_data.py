from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Department, Employee, Organization, Role, Team

# pravatar.cc serves a fixed set of ~70 numbered placeholder headshots
# purpose-built for mock/demo data like this — not photos of real,
# identifiable people tied to these (also fictional) names. Deterministic
# per index, so the same seed always renders the same faces.
def _avatar_url(index: int) -> str:
    return f"https://i.pravatar.cc/300?img={index}"


async def _ensure_departments(
    db: AsyncSession, organization_id: str, departments_by_name: dict[str, str]
) -> dict[str, Department]:
    """Get-or-create by (organization_id, name) — mirrors
    seed/capabilities.py's ensure_capabilities_seeded idempotent
    pattern: query what already exists, skip it, only add and flush
    what's actually missing. Returns every requested name mapped to its
    Department row, whether it already existed or was just created, so
    callers can immediately reference `.id` regardless of which case
    applied.

    Deliberately separate from the raw `Department(...)` + `db.add()`
    calls seed_demo_data uses for Engineering/Products/Finance above —
    those are only ever reached once per database at all (the
    lifespan caller in main.py never runs seed_demo_data a second time
    against a database that already has an Organization), so leaving
    them untouched is correct; this helper exists specifically so the
    five newly-added departments can be verified idempotent on their
    own, independent of that outer guarantee.
    """
    result = await db.execute(select(Department).where(Department.organization_id == organization_id))
    existing = {d.name: d for d in result.scalars().all()}

    created = False
    for name, description in departments_by_name.items():
        if name in existing:
            continue
        department = Department(organization_id=organization_id, name=name, description=description)
        db.add(department)
        existing[name] = department
        created = True

    if created:
        await db.flush()
    return existing


async def seed_demo_data(db: AsyncSession) -> None:
    """Creates the MVP demo dataset: Kowri Technologies / Engineering /
    Nelikem Agbanu (TechOps / Monitoring Engineer, the demo identity —
    see DEMO_EMPLOYEE_EMAIL), managed by Kofi Asamoah (VP of
    Engineering), supervised by Catherine Amarteifio (Lead Technology
    Operations Engineer). The roster is the real Engineering Department
    Profile — no placeholder/fictional employees are seeded. No demo
    Missions are seeded either — the Missions feature/admin page/
    onboarding scene stay fully intact, just empty of placeholder
    content until real missions are added (via POST /missions).
    readiness_service.py treats zero required missions as vacuously
    satisfied by design, so this doesn't block onboarding readiness."""

    org = Organization(name="Kowri Technologies", slug="kowri-technologies")
    db.add(org)
    await db.flush()

    engineering = Department(
        organization_id=org.id,
        name="Engineering",
        description="Builds and operates Kowri's financial services platform — payments, credit, "
        "and merchant tools used across Africa.",
    )
    db.add(engineering)
    await db.flush()

    # Matches Nelikem Agbanu's real title below — the demo identity
    # needs a real role_id, not just a job_title string, since
    # role-based Quest assignment/eligibility (QuestAssignment's ROLE
    # type) matches on role_id.
    role_techops_monitoring = Role(
        department_id=engineering.id,
        title="TechOps / Monitoring Engineer",
        level="mid",
        description="Monitors and operates Kowri's platform infrastructure.",
    )
    db.add(role_techops_monitoring)
    await db.flush()

    # The real Engineering Department Profile — the current, active
    # roster. `team` matches the Team rows created below verbatim.
    # manager_id/supervisor_id follow a department-level/team-level
    # split (manager = department-level lead, supervisor = team-level
    # lead): Kofi, as VP of Engineering,
    # is manager for every team below Leadership & Delivery; each
    # team's own "Lead" (Catherine for TechOps, Ishvi for Security &
    # IT) is supervisor for their team's other members. No hierarchy is
    # invented beyond what the titles themselves already state —
    # Leadership & Delivery's own three members (Kofi/Araba/Henry) are
    # left without a manager_id, since nothing in the profile states
    # their relative seniority to each other.
    kofi = Employee(
        organization_id=org.id,
        department_id=engineering.id,
        full_name="Kofi Asamoah",
        email="kofi.asamoah@buddy.dev",
        job_title="VP of Engineering / Engineering Lead",
        team="Leadership & Delivery",
        employment_type="full_time",
        start_date=date(2020, 1, 6),
        status="active",
        avatar_url=_avatar_url(21),
    )
    araba = Employee(
        organization_id=org.id,
        department_id=engineering.id,
        full_name="Araba Amuasi",
        email="araba.amuasi@buddy.dev",
        job_title="Delivery & Scrum Lead",
        team="Leadership & Delivery",
        employment_type="full_time",
        start_date=date(2020, 9, 14),
        status="active",
        avatar_url=_avatar_url(23),
    )
    henry = Employee(
        organization_id=org.id,
        department_id=engineering.id,
        full_name="Henry Sampson",
        email="henry.sampson@buddy.dev",
        job_title="Chief Engineering Officer (Chief Technology / Technical Officer)",
        team="Leadership & Delivery",
        employment_type="full_time",
        start_date=date(2019, 11, 4),
        status="active",
        avatar_url=_avatar_url(25),
    )
    db.add_all([kofi, araba, henry])
    await db.flush()

    catherine = Employee(
        organization_id=org.id,
        department_id=engineering.id,
        manager_id=kofi.id,
        full_name="Catherine Amarteifio",
        email="catherine.amarteifio@buddy.dev",
        job_title="Lead Technology Operations Engineer",
        team="Technology Operations (TechOps)",
        employment_type="full_time",
        start_date=date(2021, 2, 1),
        status="active",
        avatar_url=_avatar_url(27),
    )
    ishvi = Employee(
        organization_id=org.id,
        department_id=engineering.id,
        manager_id=kofi.id,
        full_name="Ishvi Aculey",
        email="ishvi.aculey@buddy.dev",
        job_title="Lead Security & IT Engineer",
        team="Security & IT (SIT)",
        employment_type="full_time",
        start_date=date(2021, 4, 19),
        status="active",
        avatar_url=_avatar_url(29),
    )
    db.add_all([catherine, ishvi])
    await db.flush()

    # Nelikem is the new demo identity — see DEMO_EMPLOYEE_EMAIL in
    # config.py, updated to point here. status="onboarding" and
    # start_date=today mirror exactly what Michael Mensah (the previous
    # demo identity) had, for the same reason: this is the one employee
    # /onboarding/bundle/demo and the whole unauthenticated demo flow
    # resolve through, so it must look like someone genuinely mid-
    # onboarding, not an already-settled employee.
    nelikem = Employee(
        organization_id=org.id,
        department_id=engineering.id,
        role_id=role_techops_monitoring.id,
        manager_id=kofi.id,
        supervisor_id=catherine.id,
        full_name="Nelikem Agbanu",
        email="nelikem.agbanu@buddy.dev",
        job_title="TechOps / Monitoring Engineer",
        team="Technology Operations (TechOps)",
        employment_type="full_time",
        start_date=date.today(),
        status="onboarding",
        avatar_url=_avatar_url(31),
    )
    db.add(nelikem)
    await db.flush()

    new_roster = [
        # Software Engineering & Platform — no named team lead in the
        # profile, so Kofi (department-level VP) is manager, no
        # supervisor.
        Employee(
            organization_id=org.id,
            department_id=engineering.id,
            manager_id=kofi.id,
            full_name="Michael Ato Hutchful",
            email="michael.hutchful@buddy.dev",
            job_title="Senior Software / Platform Engineer",
            team="Software Engineering & Platform",
            employment_type="full_time",
            start_date=date(2021, 5, 10),
            status="active",
            avatar_url=_avatar_url(53),
        ),
        Employee(
            organization_id=org.id,
            department_id=engineering.id,
            manager_id=kofi.id,
            full_name="Ebenezer Ohene-Adutwum",
            email="ebenezer.ohene-adutwum@buddy.dev",
            job_title="Software / Platform Engineer",
            team="Software Engineering & Platform",
            employment_type="full_time",
            start_date=date(2022, 3, 7),
            status="active",
            avatar_url=_avatar_url(55),
        ),
        Employee(
            organization_id=org.id,
            department_id=engineering.id,
            manager_id=kofi.id,
            full_name="Isaac Nii-Laye Laryea",
            email="isaac.laryea@buddy.dev",
            job_title="Software Engineer",
            team="Software Engineering & Platform",
            employment_type="full_time",
            start_date=date(2022, 8, 22),
            status="active",
            avatar_url=_avatar_url(57),
        ),
        Employee(
            organization_id=org.id,
            department_id=engineering.id,
            manager_id=kofi.id,
            full_name="Kelvin Wise Amenya",
            email="kelvin.amenya@buddy.dev",
            job_title="Software Engineer",
            team="Software Engineering & Platform",
            employment_type="full_time",
            start_date=date(2023, 2, 13),
            status="active",
            avatar_url=_avatar_url(59),
        ),
        Employee(
            organization_id=org.id,
            department_id=engineering.id,
            manager_id=kofi.id,
            full_name="Seth Kotey",
            email="seth.kotey@buddy.dev",
            job_title="Software Engineer",
            team="Software Engineering & Platform",
            employment_type="full_time",
            start_date=date(2023, 6, 5),
            status="active",
            avatar_url=_avatar_url(61),
        ),
        # Technology Operations (TechOps) — Catherine (created above) is
        # supervisor for the rest of this team.
        Employee(
            organization_id=org.id,
            department_id=engineering.id,
            manager_id=kofi.id,
            supervisor_id=catherine.id,
            full_name="Prince Amponsah",
            email="prince.amponsah@buddy.dev",
            job_title="Technology Operations & Support Engineer II",
            team="Technology Operations (TechOps)",
            employment_type="full_time",
            start_date=date(2021, 10, 18),
            status="active",
            avatar_url=_avatar_url(63),
        ),
        Employee(
            organization_id=org.id,
            department_id=engineering.id,
            manager_id=kofi.id,
            supervisor_id=catherine.id,
            full_name="Philip Kofi Aboagye",
            email="philip.aboagye@buddy.dev",
            job_title="TechOps / Operations Engineer",
            team="Technology Operations (TechOps)",
            employment_type="full_time",
            start_date=date(2022, 1, 24),
            status="active",
            avatar_url=_avatar_url(65),
        ),
        Employee(
            organization_id=org.id,
            department_id=engineering.id,
            manager_id=kofi.id,
            supervisor_id=catherine.id,
            full_name="Lawrence Kofi Mensah",
            email="lawrence.mensah@buddy.dev",
            job_title="TechOps / Monitoring & Operations Engineer",
            team="Technology Operations (TechOps)",
            employment_type="full_time",
            start_date=date(2022, 9, 12),
            status="active",
            avatar_url=_avatar_url(67),
        ),
        Employee(
            organization_id=org.id,
            department_id=engineering.id,
            manager_id=kofi.id,
            supervisor_id=catherine.id,
            full_name="William Akwasi Adu-Donkor",
            email="william.adu-donkor@buddy.dev",
            job_title="Operations Engineer",
            team="Technology Operations (TechOps)",
            employment_type="full_time",
            start_date=date(2023, 4, 3),
            status="active",
            avatar_url=_avatar_url(2),
        ),
        # Security & IT (SIT) — Ishvi (created above) is supervisor for
        # the rest of this team.
        Employee(
            organization_id=org.id,
            department_id=engineering.id,
            manager_id=kofi.id,
            supervisor_id=ishvi.id,
            full_name="Kwame Afranie",
            email="kwame.afranie@buddy.dev",
            job_title="Security & IT Engineer",
            team="Security & IT (SIT)",
            employment_type="full_time",
            start_date=date(2022, 5, 16),
            status="active",
            avatar_url=_avatar_url(4),
        ),
        Employee(
            organization_id=org.id,
            department_id=engineering.id,
            manager_id=kofi.id,
            supervisor_id=ishvi.id,
            full_name="Nii Osa Odoi",
            email="nii.odoi@buddy.dev",
            job_title="Security & IT Engineer",
            team="Security & IT (SIT)",
            employment_type="full_time",
            start_date=date(2023, 7, 30),
            status="active",
            avatar_url=_avatar_url(6),
        ),
    ]
    db.add_all(new_roster)
    await db.flush()

    # Phase A — Team Entity & Department -> Team Foundation. Adds the
    # Team rows the finalized Kowri org chart specifies, plus the two
    # additional departments (Products, Finance) required for two of
    # those rows to exist at all — Team.department_id is a NOT NULL FK,
    # so "Products has a Delivery team" is impossible without a real
    # Products department row first. Deliberately does NOT touch any
    # existing Employee row, Employee.team value, or the Engineering/
    # Design departments already seeded above — purely additive.
    products = Department(
        organization_id=org.id,
        name="Products",
        description="Owns Kowri's product roadmap, delivery, and customer-facing experience.",
    )
    finance = Department(
        organization_id=org.id,
        name="Finance",
        description="Owns Kowri's financial operations, including cloud cost management.",
    )
    db.add_all([products, finance])
    await db.flush()

    # Correction — Complete Kowri Department Structure. The remaining
    # five top-level departments in the finalized org chart — none of
    # them have any Team rows specified under them, so unlike Products/
    # Finance above, nothing requires them to exist before this point;
    # they're added here purely to complete the organization structure
    # itself, via the idempotent get-or-create helper above rather than
    # a raw unconditional insert (see _ensure_departments's own
    # docstring for why that distinction matters).
    await _ensure_departments(
        db,
        org.id,
        {
            "People & Culture": "Owns hiring, onboarding, and employee experience at Kowri.",
            "Sales": "Owns new business and revenue growth for Kowri's platform.",
            "Marketing": "Owns Kowri's brand, positioning, and go-to-market.",
            "Compliance": "Owns regulatory compliance across Kowri's markets.",
            "Relation Management": "Owns Kowri's key partner and merchant relationships.",
        },
    )

    # Engineering's team roster — replaces the original TechOps/Security &
    # IT/Platform Engineering placeholder set with the real Engineering
    # Department Profile's four groupings. "Technology Operations
    # (TechOps)" and "Security & IT (SIT)" carry their short forms in
    # parentheses, matching the profile document verbatim, since the
    # original short names ("TechOps"/"Security & IT") were already
    # familiar labels elsewhere in this project's own demo narrative
    # (Employee.team free-text values, mission scenario content) — kept
    # recognizable rather than dropped.
    teams = [
        Team(
            department_id=engineering.id,
            name="Leadership & Delivery",
            description="Engineering leadership and delivery/scrum management.",
        ),
        Team(
            department_id=engineering.id,
            name="Software Engineering & Platform",
            description="Product and platform software engineering.",
        ),
        Team(
            department_id=engineering.id,
            name="Technology Operations (TechOps)",
            description="Infrastructure, monitoring, and operations.",
        ),
        Team(
            department_id=engineering.id,
            name="Security & IT (SIT)",
            description="Security and internal IT.",
        ),
        Team(department_id=products.id, name="Delivery", description="Product delivery and execution."),
        Team(
            department_id=products.id,
            name="Customer Experience",
            description="Customer-facing product experience.",
        ),
        Team(department_id=finance.id, name="FinOps", description="Cloud cost and financial operations."),
    ]
    db.add_all(teams)

    await db.commit()

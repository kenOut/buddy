import random
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Department, Employee, Mission, Organization, Project, Role

# pravatar.cc serves a fixed set of ~70 numbered placeholder headshots
# purpose-built for mock/demo data like this — not photos of real,
# identifiable people tied to these (also fictional) names. Deterministic
# per index, so the same seed always renders the same faces.
def _avatar_url(index: int) -> str:
    return f"https://i.pravatar.cc/300?img={index}"

# Deterministic (fixed-seed) name/title pools for generating the rest of
# Engineering's two branches. Ghanaian given/family names, matching the
# style already established by the hand-written demo employees above
# (Sarah Boateng, David Owusu, Michael Mensah, Ama Asante, Kwame Adjei).
_GIVEN_NAMES = [
    "Efua", "Kojo", "Abena", "Yaw", "Akosua", "Kwabena", "Adwoa", "Nana",
    "Kwesi", "Esi", "Kofi", "Afia", "Yaa", "Kwaku", "Akua", "Fiifi",
]
_FAMILY_NAMES = [
    "Owusu", "Bonsu", "Darko", "Tutu", "Nkrumah", "Sarpong", "Frimpong",
    "Yeboah", "Amoah", "Antwi", "Agyeman", "Baffour", "Danso", "Gyasi",
]
_FINOPS_TITLES = ["FinOps Engineer", "Cloud Cost Analyst", "FinOps Lead", "Financial Systems Engineer"]
_TECHOPS_TITLES = [
    "Cloud Infrastructure Engineer",
    "Systems Engineer",
    "Network Reliability Engineer",
    "Infrastructure Engineer",
    "Observability Engineer",
    "Reliability Engineer",
]
_FINOPS_HEADCOUNT = 4
# David, Michael, Ama, and Kwame are already TechOps — generate the
# remaining headcount to reach 10 total.
_TECHOPS_EXISTING_HEADCOUNT = 4
_TECHOPS_TOTAL_HEADCOUNT = 10


def _generate_branch_employees(
    *, org_id: str, department_id: str, manager_id: str, existing_full_names: set[str]
) -> list[Employee]:
    """Fixed-seed random generation — reproducible across restarts and
    test runs, not true nondeterministic randomness, so the demo dataset
    (and anything that snapshots it, like a screenshot or a fixture)
    stays stable."""
    rng = random.Random(42)
    used_names = set(existing_full_names)
    used_emails: set[str] = set()

    def _unique_person() -> tuple[str, str, str]:
        while True:
            given = rng.choice(_GIVEN_NAMES)
            family = rng.choice(_FAMILY_NAMES)
            full_name = f"{given} {family}"
            email = f"{given.lower()}.{family.lower()}@buddy.dev"
            if full_name not in used_names and email not in used_emails:
                used_names.add(full_name)
                used_emails.add(email)
                return full_name, email, given

    def _branch(*, team: str, count: int, titles: list[str], start_year: int) -> list[Employee]:
        people = []
        for i in range(count):
            full_name, email, _ = _unique_person()
            people.append(
                Employee(
                    organization_id=org_id,
                    department_id=department_id,
                    manager_id=manager_id,
                    full_name=full_name,
                    email=email,
                    job_title=rng.choice(titles),
                    team=team,
                    employment_type="full_time",
                    start_date=date(start_year + (i % 2), (i % 12) + 1, (i * 3 % 27) + 1),
                    status="active",
                    avatar_url=_avatar_url(rng.randint(1, 70)),
                )
            )
        return people

    return [
        *_branch(team="FinOps", count=_FINOPS_HEADCOUNT, titles=_FINOPS_TITLES, start_year=2022),
        *_branch(
            team="TechOps",
            count=_TECHOPS_TOTAL_HEADCOUNT - _TECHOPS_EXISTING_HEADCOUNT,
            titles=_TECHOPS_TITLES,
            start_year=2022,
        ),
    ]


async def seed_demo_data(db: AsyncSession) -> None:
    """Creates the MVP demo dataset: Kowri Technologies / Engineering /
    Michael Mensah (SRE), managed by Sarah, supervised by David."""

    org = Organization(name="Kowri Technologies", slug="kowri-technologies")
    db.add(org)
    await db.flush()

    engineering = Department(
        organization_id=org.id,
        name="Engineering",
        description="Builds and operates Kowri's financial services platform — payments, credit, "
        "and merchant tools used across Africa.",
    )
    design = Department(
        organization_id=org.id,
        name="Design",
        description="Owns product design for Kowri's financial super-app and its design system.",
    )
    db.add_all([engineering, design])
    await db.flush()

    role_sre = Role(
        department_id=engineering.id,
        title="Site Reliability Engineer",
        level="mid",
        description="Keeps Kowri's payments and financial services platform fast, available, and "
        "observable for customers across Africa.",
    )
    role_manager = Role(
        department_id=engineering.id,
        title="Engineering Manager",
        level="lead",
        description="Leads the Engineering department.",
    )
    role_staff_sre = Role(
        department_id=engineering.id,
        title="Staff Site Reliability Engineer",
        level="senior",
        description="Technical lead for reliability initiatives.",
    )
    db.add_all([role_sre, role_manager, role_staff_sre])
    await db.flush()

    sarah = Employee(
        organization_id=org.id,
        department_id=engineering.id,
        role_id=role_manager.id,
        full_name="Sarah Boateng",
        email="sarah.boateng@buddy.dev",
        job_title="Engineering Manager",
        employment_type="full_time",
        start_date=date(2021, 3, 1),
        status="active",
        avatar_url=_avatar_url(47),
    )
    db.add(sarah)
    await db.flush()

    david = Employee(
        organization_id=org.id,
        department_id=engineering.id,
        role_id=role_staff_sre.id,
        manager_id=sarah.id,
        full_name="David Owusu",
        email="david.owusu@buddy.dev",
        job_title="Staff Site Reliability Engineer",
        team="TechOps",
        employment_type="full_time",
        start_date=date(2021, 8, 15),
        status="active",
        avatar_url=_avatar_url(12),
    )
    db.add(david)
    await db.flush()

    michael = Employee(
        organization_id=org.id,
        department_id=engineering.id,
        role_id=role_sre.id,
        manager_id=sarah.id,
        supervisor_id=david.id,
        full_name="Michael Mensah",
        email="michael.mensah@buddy.dev",
        job_title="Site Reliability Engineer",
        team="TechOps",
        employment_type="full_time",
        start_date=date.today(),
        status="onboarding",
        avatar_url=_avatar_url(33),
    )
    db.add(michael)

    teammates = [
        Employee(
            organization_id=org.id,
            department_id=engineering.id,
            role_id=role_sre.id,
            manager_id=sarah.id,
            supervisor_id=david.id,
            full_name="Ama Asante",
            email="ama.asante@buddy.dev",
            job_title="DevOps Engineer",
            team="TechOps",
            employment_type="full_time",
            start_date=date(2022, 6, 1),
            status="active",
            avatar_url=_avatar_url(5),
        ),
        Employee(
            organization_id=org.id,
            department_id=engineering.id,
            role_id=role_sre.id,
            manager_id=sarah.id,
            supervisor_id=david.id,
            full_name="Kwame Adjei",
            email="kwame.adjei@buddy.dev",
            job_title="Platform Engineer",
            team="TechOps",
            employment_type="full_time",
            start_date=date(2023, 1, 10),
            status="active",
            avatar_url=_avatar_url(15),
        ),
    ]
    db.add_all(teammates)
    await db.flush()

    # Engineering has two branches: FinOps (cloud cost/financial
    # operations) and TechOps (infrastructure/reliability). David,
    # Michael, Ama, and Kwame above are TechOps's first four; the rest of
    # each branch's roster is generated here — deterministically random
    # (a fixed seed, not true nondeterministic randomness) so the demo
    # dataset stays reproducible across restarts and test runs rather
    # than silently changing every time the app boots.
    branch_employees = _generate_branch_employees(
        org_id=org.id,
        department_id=engineering.id,
        manager_id=sarah.id,
        existing_full_names={"Sarah Boateng", "David Owusu", "Michael Mensah", "Ama Asante", "Kwame Adjei"},
    )
    db.add_all(branch_employees)
    await db.flush()

    atlas_project = Project(
        department_id=engineering.id,
        name="Automation Fraud Detection",
        description="Automated fraud-detection and risk-scoring tooling protecting transactions "
        "across Kowri's payments platform.",
    )
    onboarding_project = Project(
        department_id=engineering.id,
        name="Ecosystems Integration",
        description="Integrations connecting Kowri to banking partners, mobile money providers, "
        "and payment networks across Africa.",
    )
    db.add_all([atlas_project, onboarding_project])
    await db.flush()

    missions = [
        Mission(
            department_id=engineering.id,
            project_id=onboarding_project.id,
            title="Set up your local dev environment",
            description="Install the Kowri CLI, clone the platform repos, and run the bootstrap script.",
            mission_type="setup",
            estimated_minutes=45,
            sort_order=1,
            workspace_type="reflection",
        ),
        Mission(
            department_id=engineering.id,
            project_id=atlas_project.id,
            title="Read the on-call handbook",
            description="Understand escalation paths, severity levels, and the incident response process.",
            mission_type="reading",
            estimated_minutes=20,
            sort_order=2,
            workspace_type="quiz",
        ),
        Mission(
            department_id=engineering.id,
            project_id=onboarding_project.id,
            title="Meet your onboarding buddy",
            description="Grab 15 minutes with your buddy to ask anything about the team.",
            mission_type="meeting",
            estimated_minutes=15,
            sort_order=3,
            workspace_type="reflection",
        ),
        Mission(
            department_id=engineering.id,
            project_id=onboarding_project.id,
            title="Complete security & compliance training",
            description="Finish the mandatory security awareness and data handling training.",
            mission_type="training",
            estimated_minutes=30,
            sort_order=4,
            workspace_type="quiz",
        ),
        Mission(
            department_id=engineering.id,
            project_id=atlas_project.id,
            title="Ship your first change to staging",
            description="Open a small PR against Atlas and deploy it to the staging environment.",
            mission_type="task",
            estimated_minutes=60,
            sort_order=5,
            workspace_type="reflection",
        ),
        Mission(
            department_id=engineering.id,
            project_id=onboarding_project.id,
            title="1:1 with your manager",
            description="Set expectations and goals for your first 30 days with Sarah.",
            mission_type="meeting",
            estimated_minutes=30,
            sort_order=6,
            workspace_type="reflection",
        ),
        Mission(
            department_id=engineering.id,
            project_id=atlas_project.id,
            title="Diagnose the checkout latency spike",
            description="Customers are seeing slow checkouts. Use the metrics, logs, service map, "
            "and timeline to find the affected service and root cause.",
            mission_type="task",
            estimated_minutes=40,
            sort_order=7,
            required=True,
            workspace_type="investigation",
        ),
        # SRE/DevOps-technical missions — real production-shaped incidents
        # (crash loop, bad rollout) with deterministic grading via
        # mission_scenarios.py, same pattern as the checkout-latency
        # mission above. Marked required=True: these three are the ones
        # readiness_service.py now gates on (see its module docstring) —
        # the softer setup/reading/meeting/training missions above stay
        # optional checklist items.
        Mission(
            department_id=engineering.id,
            project_id=atlas_project.id,
            title="Investigate the payment-worker crash loop",
            description="A background worker keeps restarting after this morning's deploy. Use "
            "the metrics, logs, service map, and timeline to find the affected service and "
            "root cause before it becomes customer-facing.",
            mission_type="task",
            estimated_minutes=40,
            sort_order=8,
            required=True,
            workspace_type="investigation",
        ),
        Mission(
            department_id=engineering.id,
            project_id=onboarding_project.id,
            title="Triage the failed production rollout",
            description="A deploy just spiked error rates and the team is deciding whether to roll "
            "back. Use the metrics, logs, service map, and timeline to find out what's actually "
            "broken before that call gets made.",
            mission_type="task",
            estimated_minutes=40,
            sort_order=9,
            required=True,
            workspace_type="investigation",
        ),
    ]
    db.add_all(missions)

    await db.commit()

# Buddy (Heimdall) — AI-Powered Employee Onboarding

Buddy is an end-to-end onboarding experience for Kowri Technologies: a guided,
gamified journey (department → team → reporting line → role → missions →
assessment) backed by a manager-facing admin portal. Missions are real work —
investigations with deterministic grading, comprehension quizzes, and freeform
reflections read live by an AI-evaluation pipeline — not checklists. Completing
required Quests and Missions is what determines an employee's *readiness*,
which in turn drives automated workspace access.

**Stack:** FastAPI (async SQLAlchemy 2.0, SQLite for local dev / Postgres via
Supabase in production) + Next.js 16 (App Router, TypeScript, Tailwind v4,
Motion).

## Project layout

```
BuddyKowri/
├─ database/
│  └─ schema.sql, seed.sql        # Historical/reference snapshot only (see "Database migrations") — SQLite auto-creates its own
├─ backend/                       FastAPI
│  ├─ alembic/                    # Postgres migrations (source of truth for production schema — see "Database migrations")
│  ├─ app/
│  │  ├─ main.py                  # App factory, CORS, startup seed
│  │  ├─ core/config.py           # Settings (env-driven)
│  │  ├─ models/ · schemas/ · services/
│  │  ├─ api/v1/endpoints/        # organizations, employees, missions, quests, onboarding, admin, ...
│  │  └─ seed/seed_data.py        # Demo data loader (Michael Mensah et al.)
│  ├─ tests/                      # pytest suite (800+ tests)
│  └─ requirements.txt
└─ frontend/                      Next.js 16 + TypeScript + Tailwind + Motion
   └─ src/
      ├─ app/
      │  ├─ onboarding/           # Employee experience — /onboarding
      │  └─ admin/                # Manager portal — /admin
      ├─ components/
      └─ lib/                     # API client, types, onboarding context
```

## Prerequisites

- **Python 3.11+**
- **Node.js 20+** and npm
- No database install needed for local dev — the backend uses a local SQLite
  file by default and creates/seeds it automatically on first run.

## Setup

Clone the repo, then set up each side.

### 1. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # defaults are already fine for local dev
```

### 2. Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local   # or create it manually — see below
```

`frontend/.env.local`:

```
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

## Running the application

Run both servers, each in its own terminal.

**Backend** (from `backend/`, with the venv activated):

```bash
uvicorn app.main:app --reload --port 8000
```

On first startup this creates `backend/buddy.db` and seeds it with a demo
organization (Kowri Technologies), departments, an Engineering team, missions,
and a demo employee. Health check: `curl http://localhost:8000/health`.

**Frontend** (from `frontend/`):

```bash
npm run dev
```

Then open:

- **http://localhost:3000** — landing page → "Start onboarding" walks through
  the employee journey as the seeded demo employee (Michael Mensah).
- **http://localhost:3000/admin** — manager portal. Password: `kowri-admin`
  (set via `ADMIN_PASSWORD` in `backend/.env` to change it).

To reset the demo employee's progress back to day one at any point, use the
"Reset demo" link at the bottom of the completion screen, or:

```bash
curl -X POST http://localhost:8000/api/v1/onboarding/demo/reset
```

## Running tests

```bash
cd backend
source .venv/bin/activate
pytest
```

```bash
cd frontend
npm run lint
npx tsc --noEmit
```

## Using a real Postgres/Supabase database

By default the backend points at a local SQLite file
(`DATABASE_URL=sqlite+aiosqlite:///./buddy.db`, set implicitly if
`DATABASE_URL` is unset). SQLite is for tests and local dev only — it
gets its schema from `Base.metadata.create_all(...)` on every startup
and is never touched by Alembic. To use Postgres instead:

1. In `backend/.env`, set:
   ```
   DATABASE_URL=postgresql+asyncpg://postgres:<password>@<host>:5432/postgres
   ```
2. Apply the schema with Alembic (see "Database migrations" below):
   ```bash
   cd backend
   alembic upgrade head
   ```
3. Restart the backend.

The backend never runs `Base.metadata.create_all(...)` or
`alembic upgrade head` on its own against a non-SQLite database — a
Postgres/Supabase instance is expected to already be migrated before
the app starts (see "Database migrations").

## Database migrations

Schema changes for Postgres/Supabase are managed by
[Alembic](https://alembic.sqlalchemy.org/), reading the same
SQLAlchemy models the application itself uses
(`backend/app/models/*.py`) — there is no separate, manually-maintained
schema to keep in sync. `database/schema.sql` is a historical/reference
snapshot only as of this phase; it is not applied by anything.

```bash
cd backend

alembic upgrade head       # apply all pending migrations
alembic downgrade -1       # roll back the most recent migration
alembic current            # show the revision this database is on
alembic heads               # show the latest revision(s) — must be exactly one
alembic history             # list every migration, oldest to newest
```

`DATABASE_URL` must point at a `postgresql+asyncpg://...` connection
string to run any of the above — Alembic refuses to target SQLite in
this project (SQLite has no migration history; it's re-created fresh
every time tests or local dev start).

To generate a new migration after changing a model:

```bash
alembic revision --autogenerate -m "describe the change"
```

Always read the generated migration before applying it — autogenerate
is a diffing tool, not a guarantee; review it the same way you'd review
any other generated code.

**Production deploy order** — the application never migrates its own
database:

```text
Build the application
        ↓
Run `alembic upgrade head` (a separate migration step/job)
        ↓
Start the application
```

Running multiple application instances is safe with this order:
migration happens once, before any instance starts, so instances never
race each other to alter the schema.

## Configuration reference

| Variable (backend `.env`) | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | SQLite file | SQLAlchemy async connection string |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed frontend origin(s) |
| `DEMO_EMPLOYEE_EMAIL` | `michael.mensah@buddy.dev` | Who `/onboarding/bundle/demo` resolves to |
| `ADMIN_PASSWORD` | `kowri-admin` | Manager portal login |
| `ADMIN_SESSION_SECRET` | dev-only value | Signs the admin session cookie — override in production |
| `AI_PROVIDER` | `mock` | AI evaluation provider — `mock` is a deterministic, rule-based stand-in (no external API key required); implement the `AIProvider` protocol in `app/services/ai_provider.py` to add a real one |
| `WORKSPACE_PROVIDER` | `mock` | Grants workspace access once an employee is "ready" — `mock` needs no credentials; implement `WorkspaceProvider` in `app/services/workspace_provider.py` for a real Google Drive integration |

| Variable (frontend `.env.local`) | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000/api/v1` | Backend base URL the frontend calls |

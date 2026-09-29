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
| `ENVIRONMENT` | `development` | `production` activates every fail-closed check below, and disables demo-data seeding (see P4.1/P5) |
| `DATABASE_URL` | SQLite file | SQLAlchemy async connection string |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed frontend origin(s), comma-separated — **required in production** |
| `TRUSTED_HOSTS` | `*` (accept any Host) | Comma-separated allowlist for the Host header, enforced by `TrustedHostMiddleware` — optional; leave unset if a reverse proxy/load balancer already validates this in front of the app |
| `MAX_REQUEST_BODY_BYTES` | `2097152` (2MB) | Backstop request body size limit (413 beyond this) |
| `ENABLE_API_DOCS` | unset (auto) | `/docs`, `/redoc`, `/openapi.json` — enabled by default outside production, disabled by default in production; set `true`/`false` to override either way |
| `DEMO_EMPLOYEE_EMAIL` | `michael.mensah@buddy.dev` | Who `/onboarding/bundle/demo` resolves to |
| `ADMIN_PASSWORD` | dev-only value | Manager portal login — **required in production** |
| `ADMIN_SESSION_SECRET` | dev-only value | Signs the admin session cookie — **required in production** |
| `EMPLOYEE_SESSION_SECRET` | dev-only value | Signs the employee session cookie — **required in production** |
| `INVITATION_TOKEN_SECRET` | dev-only value | HMACs invitation tokens at rest — **required in production** |
| `PROVISIONING_API_KEY` | dev-only value | The service-to-service provisioning credential — **required in production** |
| `APP_BASE_URL` | `http://localhost:3000` | Base URL used to build the invitation link in the welcome email — **required in production** |
| `AI_PROVIDER` | `mock` | AI evaluation provider — `mock` is a deterministic, rule-based stand-in (no external API key required); implement the `AIProvider` protocol in `app/services/ai_provider.py` to add a real one |
| `WORKSPACE_PROVIDER` | `mock` | Grants workspace access once an employee is "ready" — `mock` needs no credentials; implement `WorkspaceProvider` in `app/services/workspace_provider.py` for a real Google Drive integration |
| `EMAIL_PROVIDER` | `mock` | Sends the welcome invitation email — `mock` needs no credentials and is the default in every environment, including production, until you explicitly opt in; `smtp` (P3.1, `SMTPEmailProvider`) sends real email over SMTP — see "Email delivery" below |
| `SMTP_HOST` | unset | SMTP server host (e.g. `smtp.gmail.com`) — **required when `EMAIL_PROVIDER=smtp`** |
| `SMTP_PORT` | `587` | SMTP port (STARTTLS) |
| `SMTP_USERNAME` | unset | SMTP auth username — **required when `EMAIL_PROVIDER=smtp`** |
| `SMTP_PASSWORD` | unset | SMTP auth password (a Google **app password**, never your real Google account password — see below) — **required when `EMAIL_PROVIDER=smtp`** |
| `EMAIL_FROM` | unset | The `From` address on the sent email — **required when `EMAIL_PROVIDER=smtp`** |
| `EMAIL_FROM_NAME` | `Heimdall` | The `From` display name |

Every "**required in production**" variable above fails the app closed at
startup (a `ValueError` naming exactly which env vars are missing, never
a configured value) when `ENVIRONMENT=production` and it isn't set —
see `app/core/config.py`'s `_fail_closed_in_production`. Outside
production, all of them fall back to the same well-known dev-only
defaults this project has always used, so local dev and the test suite
need zero setup.

| Variable (frontend `.env.local`) | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000/api/v1` | Backend base URL the frontend calls |

## Email delivery

The welcome email ("Meet Heimdall", sent when an employee is provisioned)
goes through one of two providers, chosen by `EMAIL_PROVIDER`:

- **`mock` (default, every environment until you opt in).** No network
  call, no credentials. Local dev and the entire automated test suite run
  against this — `MockEmailProvider.sent_emails()` is how tests inspect
  what would have been sent. Nothing here changes what a real vendor sees.
- **`smtp` (P3.1, `SMTPEmailProvider`).** Sends a real email over SMTP
  with STARTTLS (`smtplib`/`email.message`, standard library only — no new
  dependency). Never the default; selecting it requires `SMTP_HOST`,
  `SMTP_USERNAME`, `SMTP_PASSWORD`, and `EMAIL_FROM` to all be set, or the
  app refuses to start (`Settings._require_smtp_config_when_selected`) —
  there is no silent fallback to `mock`, since that would make the app
  report `email_sent=true` while nothing was actually sent.

### Gmail / Google Workspace setup (manual/integration test path)

This is for a real end-to-end delivery test, not for CI or local dev.

1. Use a **test** Gmail or Google Workspace account — never a real
   employee's inbox, and never a production account.
2. Generate a Google **app password** for that account (Google Account →
   Security → 2-Step Verification → App passwords). **Never put your
   normal Google account password into `SMTP_PASSWORD`** — only a
   generated app password, which Google can revoke independently of your
   real login credential.
3. Set these as local environment variables (or in a git-ignored `.env` —
   never commit a filled-in value):
   ```
   EMAIL_PROVIDER=smtp
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USERNAME=<test account address>
   SMTP_PASSWORD=<the app password>
   EMAIL_FROM=<test account address>
   EMAIL_FROM_NAME=Heimdall
   ```
4. Start the backend with those variables set, provision a test employee
   through the normal flow, and check the test inbox for the welcome
   email. Click "Meet Heimdall" from the same machine/browser the app is
   running on — if `APP_BASE_URL` still points at `http://localhost:3000`,
   the link will only work from that machine, not from another device.

No database migration is needed to switch providers — this is
application-layer configuration only.

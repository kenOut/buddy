-- Buddy Onboarding System — Supabase/Postgres schema
-- Run in the Supabase SQL editor, or via `supabase db push`.
-- Mirrors backend/app/models/*.py (SQLAlchemy uses portable String(36) UUIDs
-- so the same models also run on SQLite for local dev without Supabase).

create extension if not exists pgcrypto;

-- ── organizations ────────────────────────────────────────────────
create table if not exists organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  slug text not null unique,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ── departments ──────────────────────────────────────────────────
create table if not exists departments (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  name text not null,
  description text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, name)
);

-- ── roles ────────────────────────────────────────────────────────
create table if not exists roles (
  id uuid primary key default gen_random_uuid(),
  department_id uuid not null references departments(id) on delete cascade,
  title text not null,
  level text,
  description text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ── employees ────────────────────────────────────────────────────
create table if not exists employees (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  department_id uuid references departments(id) on delete set null,
  role_id uuid references roles(id) on delete set null,
  manager_id uuid references employees(id) on delete set null,
  supervisor_id uuid references employees(id) on delete set null,
  full_name text not null,
  email text not null unique,
  job_title text,
  team text, -- sub-team/branch within the department (e.g. "FinOps"/"TechOps"), display-only
  employment_type text not null default 'full_time',
  start_date date,
  avatar_url text,
  status text not null default 'invited'
    check (status in ('invited', 'onboarding', 'active')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ── projects ─────────────────────────────────────────────────────
create table if not exists projects (
  id uuid primary key default gen_random_uuid(),
  department_id uuid not null references departments(id) on delete cascade,
  name text not null,
  description text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ── missions ─────────────────────────────────────────────────────
create table if not exists missions (
  id uuid primary key default gen_random_uuid(),
  project_id uuid references projects(id) on delete set null,
  department_id uuid references departments(id) on delete set null,
  title text not null,
  description text,
  mission_type text not null default 'task'
    check (mission_type in ('task', 'reading', 'setup', 'meeting', 'training')),
  estimated_minutes integer not null default 15,
  sort_order integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ── mission_assignments ──────────────────────────────────────────
create table if not exists mission_assignments (
  id uuid primary key default gen_random_uuid(),
  mission_id uuid not null references missions(id) on delete cascade,
  employee_id uuid not null references employees(id) on delete cascade,
  onboarding_session_id uuid references onboarding_sessions(id) on delete set null,
  status text not null default 'pending'
    check (status in ('pending', 'in_progress', 'completed', 'skipped')),
  assigned_at timestamptz not null default now(),
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (mission_id, employee_id)
);

-- ── mission_attempts ─────────────────────────────────────────────
-- One row per (mission, employee): the interactive investigation-mission
-- workspace (Phase 2B) upserts this same row through its whole lifecycle
-- rather than inserting a new one per attempt.
create table if not exists mission_attempts (
  id uuid primary key default gen_random_uuid(),
  mission_id uuid not null references missions(id) on delete cascade,
  employee_id uuid not null references employees(id) on delete cascade,
  status text not null default 'not_started'
    check (status in ('not_started', 'in_progress', 'submitted', 'completed')),
  started_at timestamptz,
  completed_at timestamptz,
  affected_service text,
  likely_cause text,
  reasoning text,
  evidence_viewed jsonb not null default '[]'::jsonb,
  score numeric,
  passed boolean,
  feedback text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (mission_id, employee_id)
);

-- ── onboarding_sessions ──────────────────────────────────────────
create table if not exists onboarding_sessions (
  id uuid primary key default gen_random_uuid(),
  employee_id uuid not null references employees(id) on delete cascade,
  current_scene text not null default 'welcome'
    check (current_scene in
      ('welcome','department','team','reporting_line','role','missions','assessment','completion')),
  status text not null default 'not_started'
    check (status in ('not_started', 'in_progress', 'completed')),
  progress_percent integer not null default 0,
  started_at timestamptz,
  completed_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- mission_assignments references onboarding_sessions, which is declared after it above;
-- add the FK now that both tables exist (kept separate to preserve simple top-to-bottom reading).
alter table mission_assignments
  drop constraint if exists mission_assignments_onboarding_session_id_fkey;
alter table mission_assignments
  add constraint mission_assignments_onboarding_session_id_fkey
  foreign key (onboarding_session_id) references onboarding_sessions(id) on delete set null;

-- ── assessments ──────────────────────────────────────────────────
create table if not exists assessments (
  id uuid primary key default gen_random_uuid(),
  onboarding_session_id uuid not null references onboarding_sessions(id) on delete cascade,
  employee_id uuid not null references employees(id) on delete cascade,
  score numeric,
  passed boolean,
  answers jsonb not null default '{}'::jsonb,
  submitted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_departments_org on departments(organization_id);
create index if not exists idx_employees_org on employees(organization_id);
create index if not exists idx_employees_department on employees(department_id);
create index if not exists idx_employees_manager on employees(manager_id);
create index if not exists idx_employees_supervisor on employees(supervisor_id);
create index if not exists idx_projects_department on projects(department_id);
create index if not exists idx_missions_department on missions(department_id);
create index if not exists idx_mission_assignments_employee on mission_assignments(employee_id);
create index if not exists idx_onboarding_sessions_employee on onboarding_sessions(employee_id);
create index if not exists idx_assessments_session on assessments(onboarding_session_id);

-- ── capabilities ─────────────────────────────────────────────────
-- Phase 3A: Adaptive Capability Intelligence. Global reference table —
-- not employee/org-scoped — seeded once at startup, independent of the
-- demo org/employee seed data.
create table if not exists capabilities (
  id uuid primary key default gen_random_uuid(),
  key text not null unique,
  name text not null,
  description text,
  created_at timestamptz not null default now()
);

-- ── capability_evaluations ───────────────────────────────────────
-- One AI interpretation per completed attempt (idempotent — at most one
-- per mission_attempt_id, and separately at most one per
-- quest_attempt_id; see the partial unique indexes below). Raw provider
-- output is kept separate from the validated structured result for
-- auditability.
--
-- Phase 3B Stage 5: generalized to support either a mission attempt or a
-- quest attempt — exactly one of mission_attempt_id/quest_attempt_id is
-- populated (CHECK below). quest_attempt_id's FK is added later in this
-- file via ALTER TABLE, once quest_attempts exists (same forward-
-- reference pattern already used for mission_assignments ->
-- onboarding_sessions above).
create table if not exists capability_evaluations (
  id uuid primary key default gen_random_uuid(),
  mission_attempt_id uuid references mission_attempts(id) on delete cascade,
  quest_attempt_id uuid,
  employee_id uuid not null references employees(id) on delete cascade,
  model text not null,
  prompt_version text not null,
  evaluation_version text not null,
  raw_response text not null,
  structured_result jsonb not null,
  created_at timestamptz not null default now(),
  constraint ck_capability_evaluation_single_attempt check (
    (mission_attempt_id is not null and quest_attempt_id is null)
    or (mission_attempt_id is null and quest_attempt_id is not null)
  )
);

create unique index if not exists uq_capability_evaluation_mission_attempt
  on capability_evaluations(mission_attempt_id) where mission_attempt_id is not null;
create unique index if not exists uq_capability_evaluation_quest_attempt
  on capability_evaluations(quest_attempt_id) where quest_attempt_id is not null;

-- ── capability_evidence ──────────────────────────────────────────
-- One observed, explainable data point per row — never fabricated, always
-- traceable to an attempt and (for AI-sourced rows) an evaluation.
--
-- Phase 3B Stage 5: same mission_attempt_id/quest_attempt_id
-- generalization as capability_evaluations above. Existing Mission-
-- sourced rows are unaffected: mission_attempt_id keeps working exactly
-- as before, just now nullable to make room for the quest_attempt_id
-- sibling.
create table if not exists capability_evidence (
  id uuid primary key default gen_random_uuid(),
  employee_id uuid not null references employees(id) on delete cascade,
  mission_attempt_id uuid references mission_attempts(id) on delete cascade,
  quest_attempt_id uuid,
  capability_id uuid not null references capabilities(id) on delete cascade,
  evaluation_id uuid references capability_evaluations(id) on delete cascade,
  evidence_type text not null,
  observation text not null,
  strength text not null check (strength in ('DEVELOPING', 'CAPABLE', 'STRONG')),
  confidence numeric not null check (confidence >= 0 and confidence <= 1),
  source text not null check (source in ('deterministic', 'ai')),
  created_at timestamptz not null default now(),
  constraint ck_capability_evidence_single_attempt check (
    (mission_attempt_id is not null and quest_attempt_id is null)
    or (mission_attempt_id is null and quest_attempt_id is not null)
  )
);

-- ── capability_profiles ──────────────────────────────────────────
-- One row per (employee, capability), upserted as new evidence arrives —
-- a rollup, not raw data. NOT_OBSERVED means insufficient evidence, not
-- poor performance.
create table if not exists capability_profiles (
  id uuid primary key default gen_random_uuid(),
  employee_id uuid not null references employees(id) on delete cascade,
  capability_id uuid not null references capabilities(id) on delete cascade,
  level text not null default 'NOT_OBSERVED'
    check (level in ('NOT_OBSERVED', 'DEVELOPING', 'CAPABLE', 'STRONG')),
  score numeric not null default 0,
  confidence numeric not null default 0,
  evidence_count integer not null default 0,
  updated_at timestamptz not null default now(),
  unique (employee_id, capability_id)
);

create index if not exists idx_capability_evidence_employee on capability_evidence(employee_id);
create index if not exists idx_capability_evidence_attempt on capability_evidence(mission_attempt_id);
create index if not exists idx_capability_evidence_capability on capability_evidence(capability_id);
create index if not exists idx_capability_profiles_employee on capability_profiles(employee_id);
create index if not exists idx_capability_evaluations_employee on capability_evaluations(employee_id);

-- ── quests ───────────────────────────────────────────────────────
-- Phase 3B Stage 1: the manager-authored successor to the developer-
-- defined Mission catalog. Coexists with missions/mission_attempts —
-- nothing here replaces or reads from that table. Deliberately minimal:
-- identity/classification fields only. Tasks, evidence, evaluation
-- criteria, capability mapping, prerequisites and assignment are separate
-- tables added in later Phase 3B stages.
create table if not exists quests (
  id uuid primary key default gen_random_uuid(),
  project_id uuid references projects(id) on delete set null,
  department_id uuid references departments(id) on delete set null,
  created_by_employee_id uuid references employees(id) on delete set null,
  title text not null,
  description text,
  quest_type text not null
    check (quest_type in
      ('INVESTIGATE', 'TROUBLESHOOT', 'FIX', 'BUILD', 'DESIGN', 'ANALYZE', 'CREATE_SOLUTION', 'OTHER')),
  workspace_type text not null
    check (workspace_type in ('INVESTIGATION', 'DESIGN', 'BUILD', 'FIX', 'ANALYSIS', 'GENERAL')),
  difficulty text not null default 'MEDIUM'
    check (difficulty in ('EASY', 'MEDIUM', 'HARD', 'EXPERT')),
  status text not null default 'DRAFT'
    check (status in ('DRAFT', 'PUBLISHED', 'ARCHIVED')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ── quest_attempts ───────────────────────────────────────────────
-- One row per (quest, employee) — same upsert-through-the-lifecycle
-- pattern as mission_attempts. `submission` is deliberately generic
-- jsonb rather than typed columns; its structure is defined per quest
-- type in a later stage, not guessed at here.
create table if not exists quest_attempts (
  id uuid primary key default gen_random_uuid(),
  quest_id uuid not null references quests(id) on delete cascade,
  employee_id uuid not null references employees(id) on delete cascade,
  status text not null default 'NOT_STARTED'
    check (status in ('NOT_STARTED', 'IN_PROGRESS', 'SUBMITTED', 'EVALUATING', 'COMPLETED')),
  started_at timestamptz,
  completed_at timestamptz,
  submission jsonb not null default '{}'::jsonb,
  score numeric,
  passed boolean,
  feedback text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (quest_id, employee_id)
);

-- capability_evaluations/capability_evidence reference quest_attempts,
-- which is declared after them above; add those FKs now that both
-- tables exist (same deferred pattern as mission_assignments ->
-- onboarding_sessions).
alter table capability_evaluations
  drop constraint if exists capability_evaluations_quest_attempt_id_fkey;
alter table capability_evaluations
  add constraint capability_evaluations_quest_attempt_id_fkey
  foreign key (quest_attempt_id) references quest_attempts(id) on delete cascade;

alter table capability_evidence
  drop constraint if exists capability_evidence_quest_attempt_id_fkey;
alter table capability_evidence
  add constraint capability_evidence_quest_attempt_id_fkey
  foreign key (quest_attempt_id) references quest_attempts(id) on delete cascade;

create index if not exists idx_quests_project on quests(project_id);
create index if not exists idx_quests_department on quests(department_id);
create index if not exists idx_quests_created_by on quests(created_by_employee_id);
create index if not exists idx_quests_status on quests(status);
create index if not exists idx_quest_attempts_quest on quest_attempts(quest_id);
create index if not exists idx_quest_attempts_employee on quest_attempts(employee_id);
create index if not exists idx_capability_evidence_quest_attempt on capability_evidence(quest_attempt_id);
create index if not exists idx_capability_evaluations_quest_attempt on capability_evaluations(quest_attempt_id);

-- ── quest_tasks ──────────────────────────────────────────────────
-- Phase 3B Stage 2: employee-visible by definition — the work itself,
-- never evaluation content. See quest_evaluation_criteria below for the
-- structurally separate server-only counterpart.
create table if not exists quest_tasks (
  id uuid primary key default gen_random_uuid(),
  quest_id uuid not null references quests(id) on delete cascade,
  title text not null,
  description text,
  task_type text not null
    check (task_type in
      ('INVESTIGATE', 'ANALYZE', 'DESIGN', 'BUILD', 'FIX', 'EXPLAIN', 'CREATE', 'OTHER')),
  sort_order integer not null default 0,
  required boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ── quest_evidence ───────────────────────────────────────────────
-- Employee-visible by definition. There is deliberately no visibility
-- flag on this table — content a manager doesn't want the employee to
-- see belongs in quest_evaluation_criteria, a different table entirely,
-- not a hidden row here.
create table if not exists quest_evidence (
  id uuid primary key default gen_random_uuid(),
  quest_id uuid not null references quests(id) on delete cascade,
  title text not null,
  description text,
  evidence_type text not null
    check (evidence_type in
      ('METRICS', 'LOGS', 'SERVICES', 'TIMELINE', 'SCREENSHOT', 'DOCUMENT', 'CODE', 'DATASET', 'TEXT', 'OTHER')),
  content jsonb not null default '{}'::jsonb,
  sort_order integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ── quest_evaluation_criteria ────────────────────────────────────
-- Server-only. expected_answer/expected_behavior/reference_solution are
-- exactly the hidden evaluation content that must never reach an
-- employee-facing response — see app/schemas/quest_evaluation_criterion.py
-- (QuestEvaluationCriterionInternal) and app/schemas/quest.py
-- (EmployeeQuestResponse, which has no field capable of carrying this
-- table's data).
create table if not exists quest_evaluation_criteria (
  id uuid primary key default gen_random_uuid(),
  quest_id uuid not null references quests(id) on delete cascade,
  name text not null,
  description text,
  criterion_type text not null
    check (criterion_type in ('DETERMINISTIC', 'BEHAVIORAL', 'QUALITATIVE')),
  expected_answer text,
  expected_behavior text,
  reference_solution text,
  max_score numeric not null default 100 check (max_score > 0),
  sort_order integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ── quest_capabilities ───────────────────────────────────────────
-- Quest -> Capability mapping with relative weight. Points at the
-- existing, untouched Phase 3A capabilities table; deleting a Quest never
-- deletes the shared Capability row (the FK direction only cascades from
-- quests/capabilities down to this join table, never the reverse).
create table if not exists quest_capabilities (
  id uuid primary key default gen_random_uuid(),
  quest_id uuid not null references quests(id) on delete cascade,
  capability_id uuid not null references capabilities(id) on delete cascade,
  weight numeric not null default 1.0 check (weight > 0),
  created_at timestamptz not null default now(),
  unique (quest_id, capability_id)
);

create index if not exists idx_quest_tasks_quest on quest_tasks(quest_id);
create index if not exists idx_quest_evidence_quest on quest_evidence(quest_id);
create index if not exists idx_quest_evaluation_criteria_quest on quest_evaluation_criteria(quest_id);
create index if not exists idx_quest_capabilities_quest on quest_capabilities(quest_id);
create index if not exists idx_quest_capabilities_capability on quest_capabilities(capability_id);

-- ── quest_assignments ────────────────────────────────────────────
-- Phase 3B Stage 3: who is eligible to receive a Quest. Exactly one of
-- employee_id/department_id/role_id is populated, matching
-- assignment_type — enforced by the CHECK constraint below, not just API
-- validation. Uses the existing `roles` table (role_id) rather than a
-- free-text role/title column or a new role subsystem.
--
-- Eligibility is resolved dynamically at read time (see
-- app/services/quest_assignment_service.py) — this table is the sole
-- source of truth; there is no separate materialized/synced eligibility
-- table.
create table if not exists quest_assignments (
  id uuid primary key default gen_random_uuid(),
  quest_id uuid not null references quests(id) on delete cascade,
  assignment_type text not null check (assignment_type in ('EMPLOYEE', 'DEPARTMENT', 'ROLE')),
  employee_id uuid references employees(id) on delete cascade,
  department_id uuid references departments(id) on delete cascade,
  role_id uuid references roles(id) on delete cascade,
  active boolean not null default true,
  -- Phase 8B — whether this assignment is required for the target's
  -- onboarding readiness. Defaults false; existing assignments are
  -- unaffected. Lives on the assignment, not the quest, since the same
  -- quest can be required for one target and optional for another.
  required boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint ck_quest_assignment_single_target check (
    (assignment_type = 'EMPLOYEE' and employee_id is not null and department_id is null and role_id is null)
    or (assignment_type = 'DEPARTMENT' and department_id is not null and employee_id is null and role_id is null)
    or (assignment_type = 'ROLE' and role_id is not null and employee_id is null and department_id is null)
  )
);

-- Partial unique indexes — a plain UNIQUE(quest_id, employee_id) would
-- not prevent duplicates, since only one of the three target columns is
-- ever populated per row (NULL != NULL in SQL).
create unique index if not exists uq_quest_assignment_employee
  on quest_assignments(quest_id, employee_id) where assignment_type = 'EMPLOYEE';
create unique index if not exists uq_quest_assignment_department
  on quest_assignments(quest_id, department_id) where assignment_type = 'DEPARTMENT';
create unique index if not exists uq_quest_assignment_role
  on quest_assignments(quest_id, role_id) where assignment_type = 'ROLE';

create index if not exists idx_quest_assignments_quest on quest_assignments(quest_id);
create index if not exists idx_quest_assignments_employee on quest_assignments(employee_id);
create index if not exists idx_quest_assignments_department on quest_assignments(department_id);
create index if not exists idx_quest_assignments_role on quest_assignments(role_id);

-- ── recommendations ──────────────────────────────────────────────
-- Phase 6D: an append-only historical record of what Buddy recommended
-- and why. `reason`/`target_capabilities`/`capability_snapshot` are
-- captured at creation time and never rewritten — a later change in the
-- employee's capabilities must never alter what an old row says was
-- true when it was created. There is no UPDATE or DELETE statement
-- anywhere in the application against this table (see
-- app/services/recommendation_service.py).
--
-- `context_hash` is a fingerprint of the deterministic inputs that
-- produced this recommendation (employee, type, quest, target
-- capabilities, and their levels at that moment) — used by
-- app/services/recommendation_persistence.py to decide whether a fresh
-- GET should reuse the employee's most recent row of this type or write
-- a new historical one. It is deliberately NOT a unique constraint: the
-- same quest, or even the same hash, may legitimately recur in a later,
-- genuinely distinct development cycle.
create table if not exists recommendations (
  id uuid primary key default gen_random_uuid(),
  employee_id uuid not null references employees(id) on delete cascade,
  quest_id uuid not null references quests(id) on delete cascade,
  recommendation_type text not null default 'NEXT_QUEST'
    check (recommendation_type in ('NEXT_QUEST')),
  reason text not null,
  target_capabilities jsonb not null default '[]'::jsonb,
  capability_snapshot jsonb not null default '{}'::jsonb,
  context_hash text not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_recommendations_employee_created
  on recommendations(employee_id, created_at);
create index if not exists idx_recommendations_employee_type_created
  on recommendations(employee_id, recommendation_type, created_at);
create index if not exists idx_recommendations_quest on recommendations(quest_id);

-- ── workspace_integrations ───────────────────────────────────────
-- Phase 8B — Workspace Access Automation foundation. A department's
-- configured external workspace. One row per department (department_id
-- is unique) — the "one active/configured workspace per department for
-- MVP" scope decision, not a general many-workspaces-per-department
-- model. `external_ref` is provider plumbing (e.g. a Google shared-
-- drive/folder ID) and must never appear in an employee-facing API
-- response; only display_name/workspace_link are safe for that. No
-- credentials live on this row — provider auth material belongs in
-- server config/settings only.
create table if not exists workspace_integrations (
  id uuid primary key default gen_random_uuid(),
  department_id uuid not null unique references departments(id) on delete cascade,
  provider text not null
    check (provider in ('google_drive')),
  external_ref text not null,
  display_name text not null,
  workspace_link text not null,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ── workspace_access_grants ──────────────────────────────────────
-- Phase 8B — Workspace Access Automation foundation. One row per
-- (employee, workspace_integration) — never more, never fewer. The
-- unique constraint below is the primary idempotency mechanism for
-- granting access: whatever eventually triggers a grant attempt (not
-- implemented yet — see Phase 8C) must get-or-create against this row
-- rather than insert unconditionally. provider_ref/last_error/
-- attempt_count are operational fields for the provider integration and
-- manager-facing views only — never employee-facing.
create table if not exists workspace_access_grants (
  id uuid primary key default gen_random_uuid(),
  employee_id uuid not null references employees(id) on delete cascade,
  workspace_integration_id uuid not null references workspace_integrations(id) on delete cascade,
  status text not null default 'PENDING'
    check (status in ('PENDING', 'GRANTED', 'FAILED', 'REVOKED')),
  requested_at timestamptz not null default now(),
  granted_at timestamptz,
  provider_ref text,
  last_error text,
  attempt_count integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (employee_id, workspace_integration_id)
);

create index if not exists idx_workspace_access_grants_employee on workspace_access_grants(employee_id);
create index if not exists idx_workspace_access_grants_integration
  on workspace_access_grants(workspace_integration_id);

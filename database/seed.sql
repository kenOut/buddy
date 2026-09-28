-- Buddy demo data — mirrors backend/app/seed/seed_data.py
-- Run after database/schema.sql against a Supabase/Postgres project.
-- Uses fixed UUIDs so re-running is idempotent (ON CONFLICT DO NOTHING).

insert into organizations (id, name, slug) values
  ('00000000-0000-0000-0000-000000000001', 'Kowri Technologies', 'kowri-technologies')
on conflict (id) do nothing;

insert into departments (id, organization_id, name, description) values
  ('00000000-0000-0000-0000-000000000010', '00000000-0000-0000-0000-000000000001',
   'Engineering', 'Builds and operates Kowri''s financial services platform — payments, credit, and merchant tools used across Africa.'),
  ('00000000-0000-0000-0000-000000000011', '00000000-0000-0000-0000-000000000001',
   'Design', 'Owns product design for Kowri''s financial super-app and its design system.')
on conflict (id) do nothing;

insert into roles (id, department_id, title, level, description) values
  ('00000000-0000-0000-0000-000000000020', '00000000-0000-0000-0000-000000000010',
   'Site Reliability Engineer', 'mid', 'Keeps Kowri''s payments and financial services platform fast, available, and observable for customers across Africa.'),
  ('00000000-0000-0000-0000-000000000021', '00000000-0000-0000-0000-000000000010',
   'Engineering Manager', 'lead', 'Leads the Engineering department.'),
  ('00000000-0000-0000-0000-000000000022', '00000000-0000-0000-0000-000000000010',
   'Staff Site Reliability Engineer', 'senior', 'Technical lead for reliability initiatives.')
on conflict (id) do nothing;

insert into employees
  (id, organization_id, department_id, role_id, manager_id, supervisor_id,
   full_name, email, job_title, team, employment_type, start_date, status) values
  ('00000000-0000-0000-0000-000000000030', '00000000-0000-0000-0000-000000000001',
   '00000000-0000-0000-0000-000000000010', '00000000-0000-0000-0000-000000000021',
   null, null, 'Sarah Boateng', 'sarah.boateng@buddy.dev', 'Engineering Manager', null,
   'full_time', '2021-03-01', 'active'),
  ('00000000-0000-0000-0000-000000000031', '00000000-0000-0000-0000-000000000001',
   '00000000-0000-0000-0000-000000000010', '00000000-0000-0000-0000-000000000022',
   '00000000-0000-0000-0000-000000000030', null, 'David Owusu', 'david.owusu@buddy.dev',
   'Staff Site Reliability Engineer', 'TechOps', 'full_time', '2021-08-15', 'active'),
  ('00000000-0000-0000-0000-000000000032', '00000000-0000-0000-0000-000000000001',
   '00000000-0000-0000-0000-000000000010', '00000000-0000-0000-0000-000000000020',
   '00000000-0000-0000-0000-000000000030', '00000000-0000-0000-0000-000000000031',
   'Michael Mensah', 'michael.mensah@buddy.dev', 'Site Reliability Engineer', 'TechOps',
   'full_time', current_date, 'onboarding'),
  ('00000000-0000-0000-0000-000000000033', '00000000-0000-0000-0000-000000000001',
   '00000000-0000-0000-0000-000000000010', '00000000-0000-0000-0000-000000000020',
   '00000000-0000-0000-0000-000000000030', '00000000-0000-0000-0000-000000000031',
   'Ama Asante', 'ama.asante@buddy.dev', 'DevOps Engineer', 'TechOps', 'full_time', '2022-06-01', 'active'),
  ('00000000-0000-0000-0000-000000000034', '00000000-0000-0000-0000-000000000001',
   '00000000-0000-0000-0000-000000000010', '00000000-0000-0000-0000-000000000020',
   '00000000-0000-0000-0000-000000000030', '00000000-0000-0000-0000-000000000031',
   'Kwame Adjei', 'kwame.adjei@buddy.dev', 'Platform Engineer', 'TechOps', 'full_time', '2023-01-10', 'active'),
  -- FinOps branch (4) — Engineering's cloud cost/financial operations team.
  ('00000000-0000-0000-0000-000000000035', '00000000-0000-0000-0000-000000000001',
   '00000000-0000-0000-0000-000000000010', null, '00000000-0000-0000-0000-000000000030', null,
   'Yaw Owusu', 'yaw.owusu@buddy.dev', 'FinOps Lead', 'FinOps', 'full_time', '2022-01-01', 'active'),
  ('00000000-0000-0000-0000-000000000036', '00000000-0000-0000-0000-000000000001',
   '00000000-0000-0000-0000-000000000010', null, '00000000-0000-0000-0000-000000000030', null,
   'Nana Tutu', 'nana.tutu@buddy.dev', 'Cloud Cost Analyst', 'FinOps', 'full_time', '2023-02-04', 'active'),
  ('00000000-0000-0000-0000-000000000037', '00000000-0000-0000-0000-000000000001',
   '00000000-0000-0000-0000-000000000010', null, '00000000-0000-0000-0000-000000000030', null,
   'Yaw Agyeman', 'yaw.agyeman@buddy.dev', 'FinOps Engineer', 'FinOps', 'full_time', '2022-03-07', 'active'),
  ('00000000-0000-0000-0000-000000000038', '00000000-0000-0000-0000-000000000001',
   '00000000-0000-0000-0000-000000000010', null, '00000000-0000-0000-0000-000000000030', null,
   'Kwaku Owusu', 'kwaku.owusu@buddy.dev', 'FinOps Engineer', 'FinOps', 'full_time', '2023-04-10', 'active'),
  -- TechOps branch, remaining 6 (David/Michael/Ama/Kwame above are the first 4, for 10 total).
  ('00000000-0000-0000-0000-000000000039', '00000000-0000-0000-0000-000000000001',
   '00000000-0000-0000-0000-000000000010', null, '00000000-0000-0000-0000-000000000030', null,
   'Abena Tutu', 'abena.tutu@buddy.dev', 'Systems Engineer', 'TechOps', 'full_time', '2022-01-01', 'active'),
  ('00000000-0000-0000-0000-00000000003a', '00000000-0000-0000-0000-000000000001',
   '00000000-0000-0000-0000-000000000010', null, '00000000-0000-0000-0000-000000000030', null,
   'Efua Amoah', 'efua.amoah@buddy.dev', 'Systems Engineer', 'TechOps', 'full_time', '2023-02-04', 'active'),
  ('00000000-0000-0000-0000-00000000003b', '00000000-0000-0000-0000-000000000001',
   '00000000-0000-0000-0000-000000000010', null, '00000000-0000-0000-0000-000000000030', null,
   'Kwaku Tutu', 'kwaku.tutu@buddy.dev', 'Infrastructure Engineer', 'TechOps', 'full_time', '2022-03-07', 'active'),
  ('00000000-0000-0000-0000-00000000003c', '00000000-0000-0000-0000-000000000001',
   '00000000-0000-0000-0000-000000000010', null, '00000000-0000-0000-0000-000000000030', null,
   'Kwesi Danso', 'kwesi.danso@buddy.dev', 'Cloud Infrastructure Engineer', 'TechOps', 'full_time', '2023-04-10', 'active'),
  ('00000000-0000-0000-0000-00000000003d', '00000000-0000-0000-0000-000000000001',
   '00000000-0000-0000-0000-000000000010', null, '00000000-0000-0000-0000-000000000030', null,
   'Kwabena Baffour', 'kwabena.baffour@buddy.dev', 'Infrastructure Engineer', 'TechOps', 'full_time', '2022-05-13', 'active'),
  ('00000000-0000-0000-0000-00000000003e', '00000000-0000-0000-0000-000000000001',
   '00000000-0000-0000-0000-000000000010', null, '00000000-0000-0000-0000-000000000030', null,
   'Kofi Nkrumah', 'kofi.nkrumah@buddy.dev', 'Systems Engineer', 'TechOps', 'full_time', '2023-06-16', 'active')
on conflict (id) do nothing;

insert into projects (id, department_id, name, description) values
  ('00000000-0000-0000-0000-000000000040', '00000000-0000-0000-0000-000000000010',
   'Automation Fraud Detection', 'Automated fraud-detection and risk-scoring tooling protecting transactions across Kowri''s payments platform.'),
  ('00000000-0000-0000-0000-000000000041', '00000000-0000-0000-0000-000000000010',
   'Ecosystems Integration', 'Integrations connecting Kowri to banking partners, mobile money providers, and payment networks across Africa.')
on conflict (id) do nothing;

insert into missions
  (id, department_id, project_id, title, description, mission_type, estimated_minutes, sort_order) values
  ('00000000-0000-0000-0000-000000000050', '00000000-0000-0000-0000-000000000010',
   '00000000-0000-0000-0000-000000000041', 'Set up your local dev environment',
   'Install the Kowri CLI, clone the platform repos, and run the bootstrap script.',
   'setup', 45, 1),
  ('00000000-0000-0000-0000-000000000051', '00000000-0000-0000-0000-000000000010',
   '00000000-0000-0000-0000-000000000040', 'Read the on-call handbook',
   'Understand escalation paths, severity levels, and the incident response process.',
   'reading', 20, 2),
  ('00000000-0000-0000-0000-000000000052', '00000000-0000-0000-0000-000000000010',
   '00000000-0000-0000-0000-000000000041', 'Meet your onboarding buddy',
   'Grab 15 minutes with your buddy to ask anything about the team.',
   'meeting', 15, 3),
  ('00000000-0000-0000-0000-000000000053', '00000000-0000-0000-0000-000000000010',
   '00000000-0000-0000-0000-000000000041', 'Complete security & compliance training',
   'Finish the mandatory security awareness and data handling training.',
   'training', 30, 4),
  ('00000000-0000-0000-0000-000000000054', '00000000-0000-0000-0000-000000000010',
   '00000000-0000-0000-0000-000000000040', 'Ship your first change to staging',
   'Open a small PR against Atlas and deploy it to the staging environment.',
   'task', 60, 5),
  ('00000000-0000-0000-0000-000000000055', '00000000-0000-0000-0000-000000000010',
   '00000000-0000-0000-0000-000000000041', '1:1 with your manager',
   'Set expectations and goals for your first 30 days with Sarah.',
   'meeting', 30, 6),
  ('00000000-0000-0000-0000-000000000056', '00000000-0000-0000-0000-000000000010',
   '00000000-0000-0000-0000-000000000040', 'Diagnose the checkout latency spike',
   'Customers are seeing slow checkouts. Use the metrics, logs, service map, and timeline to find the affected service and root cause.',
   'task', 40, 7)
on conflict (id) do nothing;

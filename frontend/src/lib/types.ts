export interface Organization {
  id: string;
  name: string;
  slug: string;
  created_at: string;
  updated_at: string;
}

export interface Department {
  id: string;
  organization_id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

/** Phase 8G — manager/admin-facing workspace configuration for a
 * department. Fuller than the employee-safe EmployeeWorkspaceAccess
 * (external_ref/provider are fine here — the manager configuring this
 * row is exactly who they're for); never used on an employee-facing
 * route. "mock" is deliberately NOT a valid `provider` value — it
 * selects the provider implementation app-wide via a server setting,
 * never a specific department's stored configuration (see
 * WORKSPACE_PROVIDERS on the backend). */
export const WORKSPACE_PROVIDERS = ["google_drive"] as const;
export type WorkspaceProviderValue = (typeof WORKSPACE_PROVIDERS)[number];

export interface WorkspaceIntegration {
  id: string;
  department_id: string;
  provider: string;
  external_ref: string;
  display_name: string;
  workspace_link: string;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Role {
  id: string;
  department_id: string;
  title: string;
  level: string | null;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export type EmployeeStatus = "invited" | "onboarding" | "active" | "inactive";

export interface Employee {
  id: string;
  organization_id: string;
  department_id: string | null;
  role_id: string | null;
  manager_id: string | null;
  supervisor_id: string | null;
  full_name: string;
  email: string;
  job_title: string | null;
  team: string | null;
  employment_type: string;
  start_date: string | null;
  avatar_url: string | null;
  status: EmployeeStatus;
  identity_provider: string | null;
  external_subject: string | null;
  created_at: string;
  updated_at: string;
}

export interface EmployeeSummary {
  id: string;
  full_name: string;
  email: string;
  job_title: string | null;
  team: string | null;
  avatar_url: string | null;
}

/** Phase 8E — the employee-safe workspace-access read. GRANTED/PENDING/
 * FAILED mirror the backend grant's status; NOT_CONFIGURED has no
 * backend grant counterpart — it covers every case where nothing exists
 * to report on yet (no department, no active workspace integration, or
 * one exists but no grant has been created). Deliberately says nothing
 * about onboarding/quest readiness — see EmployeeWorkspaceAccess's
 * backend docstring. */
export type WorkspaceAccessStatus = "GRANTED" | "PENDING" | "FAILED" | "NOT_CONFIGURED";

export interface EmployeeWorkspaceAccess {
  status: WorkspaceAccessStatus;
  workspace_name: string | null;
  workspace_link: string | null;
}

export interface Project {
  id: string;
  department_id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export type MissionType = "task" | "reading" | "setup" | "meeting" | "training";

export type MissionWorkspaceType = "investigation" | "quiz" | "reflection";

export interface Mission {
  id: string;
  project_id: string | null;
  department_id: string | null;
  title: string;
  description: string | null;
  mission_type: MissionType;
  estimated_minutes: number;
  sort_order: number;
  required: boolean;
  workspace_type: MissionWorkspaceType;
  created_at: string;
  updated_at: string;
}

export type MissionAssignmentStatus = "pending" | "in_progress" | "completed" | "skipped";

export interface MissionAssignment {
  id: string;
  mission_id: string;
  employee_id: string;
  onboarding_session_id: string | null;
  status: MissionAssignmentStatus;
  assigned_at: string;
  completed_at: string | null;
  mission: Mission;
}

export type SceneKey =
  | "welcome"
  | "department"
  | "team"
  | "reporting_line"
  | "role"
  | "missions"
  | "assessment"
  | "completion";

export type SessionStatus = "not_started" | "in_progress" | "completed";

export interface OnboardingSession {
  id: string;
  employee_id: string;
  current_scene: SceneKey;
  status: SessionStatus;
  progress_percent: number;
  started_at: string | null;
  completed_at: string | null;
}

export interface AssessmentQuestionOption {
  id: string;
  label: string;
}

export interface AssessmentQuestion {
  id: string;
  prompt: string;
  options: AssessmentQuestionOption[];
}

export interface Assessment {
  id: string;
  onboarding_session_id: string;
  employee_id: string;
  score: number | null;
  passed: boolean | null;
  answers: Record<string, string>;
  submitted_at: string | null;
  created_at: string;
}

export interface OnboardingBundle {
  employee: Employee;
  organization: Organization;
  department: Department | null;
  role: Role | null;
  manager: EmployeeSummary | null;
  supervisor: EmployeeSummary | null;
  teammates: EmployeeSummary[];
  projects: Project[];
  session: OnboardingSession;
  mission_assignments: MissionAssignment[];
  assessment_questions: AssessmentQuestion[];
}

export interface EvidenceItem {
  id: string;
  label: string;
  detail: string;
}

export interface TimelineItem {
  id: string;
  time: string;
  label: string;
}

export interface MissionScenario {
  mission_id: string;
  briefing: string;
  metrics: EvidenceItem[];
  logs: EvidenceItem[];
  services: EvidenceItem[];
  timeline: TimelineItem[];
  service_options: string[];
  cause_options: string[];
}

export interface MissionQuizQuestion {
  id: string;
  prompt: string;
  options: string[];
}

export interface MissionQuiz {
  mission_id: string;
  briefing: string;
  questions: MissionQuizQuestion[];
}

export type MissionAttemptStatus = "not_started" | "in_progress" | "submitted" | "completed";

export interface MissionAttempt {
  id: string;
  mission_id: string;
  employee_id: string;
  status: MissionAttemptStatus;
  started_at: string | null;
  completed_at: string | null;
  affected_service: string | null;
  likely_cause: string | null;
  reasoning: string | null;
  evidence_viewed: string[];
  quiz_answers: Record<string, string>;
  score: number | null;
  passed: boolean | null;
  feedback: string | null;
}

export interface EmployeeOnboardingRow {
  employee: Employee;
  department: Department | null;
  session: OnboardingSession | null;
  missions_completed: number;
  missions_total: number;
}

export interface AdminOverview {
  total_employees: number;
  onboarding_in_progress: number;
  onboarding_completed: number;
  total_departments: number;
  rows: EmployeeOnboardingRow[];
}

export type CapabilityLevel = "NOT_OBSERVED" | "DEVELOPING" | "CAPABLE" | "STRONG";
export type CapabilityEvidenceStrength = "DEVELOPING" | "CAPABLE" | "STRONG";
export type CapabilityEvidenceSource = "deterministic" | "ai";

export interface Capability {
  id: string;
  key: string;
  name: string;
  description: string | null;
  created_at: string;
}

export interface CapabilityProfile {
  id: string;
  employee_id: string;
  capability_id: string;
  capability: Capability;
  level: CapabilityLevel;
  score: number;
  confidence: number;
  evidence_count: number;
  updated_at: string;
}

export interface CapabilityEvidence {
  id: string;
  employee_id: string;
  mission_attempt_id: string;
  capability_id: string;
  evaluation_id: string | null;
  evidence_type: string;
  observation: string;
  strength: CapabilityEvidenceStrength;
  confidence: number;
  source: CapabilityEvidenceSource;
  created_at: string;
}

export interface AICapabilityAssessment {
  capability: string;
  level: CapabilityEvidenceStrength;
  confidence: number;
  evidence: string;
}

export interface AIEvaluationResult {
  summary: string;
  strengths: string[];
  development_areas: string[];
  capabilities: AICapabilityAssessment[];
  recommended_focus: string;
}

export interface CapabilityEvaluation {
  id: string;
  mission_attempt_id: string;
  employee_id: string;
  model: string;
  prompt_version: string;
  evaluation_version: string;
  structured_result: AIEvaluationResult;
  created_at: string;
}

export interface NextMissionResponse {
  mission: Mission | null;
  reason: string;
  target_capabilities: string[];
}

// ---- Phase 3B: Quest ----

export type QuestType =
  | "INVESTIGATE"
  | "TROUBLESHOOT"
  | "FIX"
  | "BUILD"
  | "DESIGN"
  | "ANALYZE"
  | "CREATE_SOLUTION"
  | "OTHER";

export type QuestWorkspaceType =
  | "INVESTIGATION"
  | "DESIGN"
  | "BUILD"
  | "FIX"
  | "ANALYSIS"
  | "GENERAL"
  | "TROUBLESHOOT";
export type QuestDifficulty = "EASY" | "MEDIUM" | "HARD" | "EXPERT";
export type QuestStatus = "DRAFT" | "PUBLISHED" | "ARCHIVED";

export type QuestTaskType =
  | "INVESTIGATE"
  | "ANALYZE"
  | "DESIGN"
  | "BUILD"
  | "FIX"
  | "EXPLAIN"
  | "CREATE"
  | "OTHER";

export type QuestEvidenceType =
  | "METRICS"
  | "LOGS"
  | "SERVICES"
  | "TIMELINE"
  | "SCREENSHOT"
  | "DOCUMENT"
  | "CODE"
  | "DATASET"
  | "TEXT"
  | "OTHER";

export type QuestAttemptStatus = "NOT_STARTED" | "IN_PROGRESS" | "SUBMITTED" | "EVALUATING" | "COMPLETED";

export interface QuestTaskItem {
  id: string;
  quest_id: string;
  title: string;
  description: string | null;
  task_type: QuestTaskType;
  sort_order: number;
  required: boolean;
  created_at: string;
  updated_at: string;
}

/** `content` is deliberately a loose JSON record, not a typed shape per
 * evidence_type — the whole point of Stage 2/4's evidence model is that
 * the manager can put whatever fields make sense for a given evidence
 * item under it, and the workspace renders it generically. */
export interface QuestEvidenceItem {
  id: string;
  quest_id: string;
  title: string;
  description: string | null;
  evidence_type: QuestEvidenceType;
  content: Record<string, unknown>;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

/** The employee-safe Quest contract — structurally incapable of carrying
 * evaluation criteria (there is no field here that could hold one). */
export interface EmployeeQuest {
  id: string;
  title: string;
  description: string | null;
  quest_type: QuestType;
  workspace_type: QuestWorkspaceType;
  difficulty: QuestDifficulty;
  tasks: QuestTaskItem[];
  evidence: QuestEvidenceItem[];
  /** Phase 8H-3 — derived server-side from the same eligibility query
   * readiness itself uses. Independent of whether this Quest happens to
   * be the current recommendation, and independent of completion
   * status: a completed required Quest stays `true`. Never compute this
   * on the client — always the value the API returned. */
  required_for_readiness: boolean;
}

export interface QuestEligibility {
  eligible: boolean;
  quest_status: QuestStatus;
  matching_assignment_types: string[];
}

/** Phase 8H-4 — one card's worth of data for the employee's own Quest
 * list (GET /employees/{employee_id}/quests). Lighter than
 * `EmployeeQuest`: no tasks/evidence, since a list of cards only needs
 * enough to decide which Quest to open, not its full work content.
 * `attempt_status` is `null` when the employee has never started this
 * Quest — opening the list itself never creates an attempt. */
export interface EmployeeQuestSummary {
  id: string;
  title: string;
  description: string | null;
  quest_type: QuestType;
  difficulty: QuestDifficulty;
  required_for_readiness: boolean;
  attempt_status: QuestAttemptStatus | null;
}

/** Generic, quest-type-agnostic work record — the same three fields
 * (plus which tasks are done) regardless of whether this is an
 * INVESTIGATE, BUILD, or DESIGN quest.
 *
 * `workspace` (Phase 7 Stage 1) is the additive envelope a specialized
 * Workspace can use for its own payload — nested under one key rather
 * than flattened alongside findings/reasoning/solution, so adding a new
 * Workspace type's fields never risks colliding with these generic ones
 * or with a future Workspace's own. */
export interface QuestSubmissionData {
  findings?: string;
  reasoning?: string;
  solution?: string;
  completed_task_ids?: string[];
  workspace?: { type: QuestWorkspaceType; payload: Record<string, unknown> } | null;
}

export interface QuestAttempt {
  id: string;
  quest_id: string;
  employee_id: string;
  status: QuestAttemptStatus;
  started_at: string | null;
  completed_at: string | null;
  submission: QuestSubmissionData;
  score: number | null;
  passed: boolean | null;
  feedback: string | null;
  created_at: string;
  updated_at: string;
}

/** Phase 3B Stage 5 — the employee-safe evaluation contract. Reuses
 * AICapabilityAssessment (Phase 3A) for the capabilities array; there is
 * no field here, and no way to add one, that could carry expected_answer/
 * expected_behavior/reference_solution. */
export interface QuestEvaluationResult {
  status: QuestAttemptStatus;
  summary: string;
  strengths: string[];
  development_areas: string[];
  capabilities: AICapabilityAssessment[];
  recommended_focus: string;
  evaluated_at: string;
}

// ---- Phase 3B Stage 6A: Manager Quest Builder ----

/** The bare Quest record — no nested content. Returned by list/create/
 * update/publish/archive. */
export interface Quest {
  id: string;
  project_id: string | null;
  department_id: string | null;
  created_by_employee_id: string | null;
  title: string;
  description: string | null;
  quest_type: QuestType;
  workspace_type: QuestWorkspaceType;
  difficulty: QuestDifficulty;
  status: QuestStatus;
  created_at: string;
  updated_at: string;
}

export type QuestCriterionType = "DETERMINISTIC" | "BEHAVIORAL" | "QUALITATIVE";

/** Manager/server-only — carries expected_answer/expected_behavior/
 * reference_solution, which must never reach an employee-facing view.
 * Only ever fetched from /quests/{id}/detail, never from /quests/{id}/employee. */
export interface QuestEvaluationCriterion {
  id: string;
  quest_id: string;
  name: string;
  description: string | null;
  criterion_type: QuestCriterionType;
  expected_answer: string | null;
  expected_behavior: string | null;
  reference_solution: string | null;
  max_score: number;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface QuestCapabilityMapping {
  id: string;
  quest_id: string;
  capability_id: string;
  capability: Capability;
  weight: number;
  created_at: string;
}

export type QuestAssignmentType = "EMPLOYEE" | "DEPARTMENT" | "ROLE";

export interface QuestAssignment {
  id: string;
  quest_id: string;
  assignment_type: QuestAssignmentType;
  employee_id: string | null;
  department_id: string | null;
  role_id: string | null;
  active: boolean;
  required: boolean;
  created_at: string;
  updated_at: string;
}

/** The full manager/authoring view of a Quest — everything, including
 * hidden evaluation content. Never pass this to an employee-facing
 * component; use EmployeeQuest for that. */
export interface QuestDetail extends Quest {
  tasks: QuestTaskItem[];
  evidence: QuestEvidenceItem[];
  evaluation_criteria: QuestEvaluationCriterion[];
  capabilities: QuestCapabilityMapping[];
}

// ---- Phase 6B: Quest Quality Validation ----

export type QuestQualitySeverity = "ERROR" | "WARNING";

/** `section` matches a Builder tab key (see BuilderSectionKey in
 * BuilderNav.tsx) 1:1 — always one of "basic-info" | "challenge" |
 * "work-evidence" | "evaluation" | "capabilities" | "assign-publish" —
 * so a failing check can jump the manager straight to the right tab. */
export interface QuestQualityCheck {
  code: string;
  severity: QuestQualitySeverity;
  message: string;
  section: string;
  satisfied: boolean;
}

export interface QuestQualityValidation {
  ready: boolean;
  errors: QuestQualityCheck[];
  warnings: QuestQualityCheck[];
  checks: QuestQualityCheck[];
}

// ---- Builder input payloads ----

export interface QuestCreateInput {
  project_id?: string | null;
  department_id?: string | null;
  created_by_employee_id?: string | null;
  title: string;
  description?: string | null;
  quest_type: QuestType;
  workspace_type: QuestWorkspaceType;
  difficulty?: QuestDifficulty;
}

export interface QuestUpdateInput {
  project_id?: string | null;
  department_id?: string | null;
  created_by_employee_id?: string | null;
  title?: string;
  description?: string | null;
  quest_type?: QuestType;
  workspace_type?: QuestWorkspaceType;
  difficulty?: QuestDifficulty;
}

export interface QuestTaskInput {
  title: string;
  description?: string | null;
  task_type: QuestTaskType;
  sort_order?: number;
  required?: boolean;
}

export interface QuestEvidenceInput {
  title: string;
  description?: string | null;
  evidence_type: QuestEvidenceType;
  content?: Record<string, unknown>;
  sort_order?: number;
}

export interface QuestEvaluationCriterionInput {
  name: string;
  description?: string | null;
  criterion_type: QuestCriterionType;
  expected_answer?: string | null;
  expected_behavior?: string | null;
  reference_solution?: string | null;
  max_score?: number;
  sort_order?: number;
}

export interface QuestCapabilityInput {
  capability_id: string;
  weight?: number;
}

export interface QuestAssignmentInput {
  assignment_type: QuestAssignmentType;
  employee_id?: string | null;
  department_id?: string | null;
  role_id?: string | null;
  required?: boolean;
}

// ---- Phase 6C: Adaptive Capability Loop ----

/** Never a numeric score — one of these four labels, always paired with
 * a plain-language `reason`. CAPABLE items only ever appear in
 * `assessed_capabilities`, not in strengths/development_areas/unobserved
 * — "demonstrated capability" isn't automatically a strength or a gap. */
export type CapabilityGapCategory = "STRENGTH" | "CAPABLE" | "DEVELOPMENT_AREA" | "UNOBSERVED";

export interface CapabilityGapItem {
  capability: string;
  capability_name: string;
  current_level: CapabilityLevel;
  category: CapabilityGapCategory;
  reason: string;
}

export interface CapabilityGapAnalysis {
  employee_id: string;
  strengths: CapabilityGapItem[];
  development_areas: CapabilityGapItem[];
  unobserved: CapabilityGapItem[];
  assessed_capabilities: CapabilityGapItem[];
  generated_at: string;
}

/** `recommended_quest` is the same structurally employee-safe
 * EmployeeQuest contract the Quest Workspace itself uses — there is no
 * field here, or on that type, capable of carrying evaluation-criteria
 * internals. `target_capabilities` are capability keys (snake_case,
 * e.g. "documentation"), matching NextMissionResponse's convention. */
export interface NextQuestResponse {
  recommended_quest: EmployeeQuest | null;
  reason: string;
  target_capabilities: string[];
  gap_analysis: CapabilityGapAnalysis | null;
}

// ---- Phase 8H-1: Readiness Summary ----

/** The employee-safe, fully-derived readiness read model — mirrors
 * EmployeeReadinessSummary on the backend exactly (schemas/readiness.py).
 * Counts only; never a Quest id/title/assignment detail. `ready` is the
 * single source of truth for "is this employee ready" — never
 * recomputed or inferred client-side. */
export interface EmployeeReadinessSummary {
  ready: boolean;
  onboarding_completed: boolean;
  required_quest_count: number;
  completed_required_quest_count: number;
  remaining_required_quest_count: number;
  required_mission_count: number;
  completed_required_mission_count: number;
  remaining_required_mission_count: number;
}

// ---- Phase 6D: Development Journey ----

export type DevelopmentJourneyItemType =
  | "ONBOARDING_COMPLETED"
  | "QUEST_COMPLETED"
  | "CAPABILITY_OBSERVED"
  | "READINESS_REACHED"
  | "WORKSPACE_ACCESS_GRANTED"
  | "RECOMMENDATION";

/** One timeline entry. Structurally safe by construction — every field
 * here traces back to already employee-safe sources (Quest.title,
 * Capability.name, a persisted Recommendation.reason); there is no
 * field capable of carrying evaluation-criteria internals. */
export interface DevelopmentJourneyItem {
  id: string;
  type: DevelopmentJourneyItemType;
  timestamp: string;
  title: string;
  description: string;
  quest_id: string | null;
  quest_available: boolean | null;
  capability: string | null;
  level: CapabilityLevel | null;
  reason: string | null;
  target_capabilities: string[] | null;
  /** Phase 8H-2 — WORKSPACE_ACCESS_GRANTED only. Never carries
   * external_ref/provider/provider_ref/last_error/attempt_count —
   * those fields do not exist on this type. */
  workspace_name: string | null;
  workspace_link: string | null;
}

export interface DevelopmentJourneyResponse {
  employee_id: string;
  items: DevelopmentJourneyItem[];
}

// ---- Phase 6E: Manager Analytics ----

export interface RecentRecommendationItem {
  recommendation_id: string;
  employee_id: string;
  employee_name: string;
  quest_id: string;
  quest_title: string;
  reason: string;
  target_capabilities: string[];
  created_at: string;
}

export interface AnalyticsOverview {
  department_id: string | null;
  published_quests: number;
  draft_quests: number;
  archived_quests: number;
  active_assignment_records: number;
  employees_reached: number;
  attempts_total: number;
  attempts_not_started: number;
  attempts_in_progress: number;
  attempts_submitted: number;
  attempts_evaluating: number;
  attempts_completed: number;
  employees_with_capability_evidence: number;
  capability_observations: number;
  recommendations_generated: number;
  employees_with_development_history: number;
  recent_recommendations: RecentRecommendationItem[];
}

/** Deterministic operational patterns (never a verdict) — see
 * analytics_service.py's `_quest_signals` for the exact, fixed
 * thresholds behind each code. */
export type QuestAnalyticsSignal =
  | "ZERO_ATTEMPTS"
  | "SUBMITTED_NOT_COMPLETED"
  | "NO_EVIDENCE_GENERATED"
  | "NEVER_RECOMMENDED"
  | "FREQUENTLY_RECOMMENDED"
  | "HIGH_COMPLETION_ACTIVITY";

export interface QuestAnalyticsSummary {
  quest_id: string;
  title: string;
  quest_type: QuestType;
  status: QuestStatus;
  difficulty: QuestDifficulty;
  project_id: string | null;
  project_name: string | null;
  capability_count: number;
  assigned_employees: number;
  attempts_total: number;
  attempts_completed: number;
  completion_rate: number | null;
  evidence_count: number;
  recommendation_count: number;
  signals: QuestAnalyticsSignal[];
}

export interface AnalyticsQuestsResponse {
  department_id: string | null;
  quests: QuestAnalyticsSummary[];
}

export interface QuestCapabilityEvidenceBreakdown {
  capability_key: string;
  capability_name: string;
  evidence_count: number;
}

export interface QuestDetailAnalytics {
  quest_id: string;
  title: string;
  quest_type: QuestType;
  status: QuestStatus;
  difficulty: QuestDifficulty;
  project_id: string | null;
  project_name: string | null;
  assigned_employees: number;
  attempts_total: number;
  attempts_not_started: number;
  attempts_in_progress: number;
  attempts_submitted: number;
  attempts_evaluating: number;
  attempts_completed: number;
  completion_rate: number | null;
  evidence_count: number;
  capability_breakdown: QuestCapabilityEvidenceBreakdown[];
  evaluation_criteria_count: number;
  recommendation_count: number;
  signals: QuestAnalyticsSignal[];
}

export interface CapabilityLevelBreakdownItem {
  level: CapabilityLevel;
  employee_count: number;
}

export interface QuestEvidenceSourceItem {
  quest_id: string;
  quest_title: string;
  evidence_count: number;
}

export interface CapabilityAnalyticsSummary {
  capability_id: string;
  capability_key: string;
  capability_name: string;
  total_employees: number;
  observed_employees: number;
  not_observed_employees: number;
  level_breakdown: CapabilityLevelBreakdownItem[];
  development_area_employees: number;
  quests_producing_evidence: QuestEvidenceSourceItem[];
}

export interface AnalyticsCapabilitiesResponse {
  department_id: string | null;
  capabilities: CapabilityAnalyticsSummary[];
}

export interface DevelopmentSignalItem {
  capability_id: string;
  capability_key: string;
  capability_name: string;
  employee_count: number;
}

export interface AnalyticsDevelopmentSignalsResponse {
  department_id: string | null;
  development_areas: DevelopmentSignalItem[];
}

export interface EmployeeCapabilityAnalyticsSummary {
  capability_key: string;
  capability_name: string;
  level: CapabilityLevel;
  category: CapabilityGapCategory;
  evidence_count: number;
}

export interface EmployeeQuestActivityAnalyticsItem {
  quest_id: string;
  quest_title: string;
  status: QuestAttemptStatus;
  completed_at: string | null;
}

export interface EmployeeRecommendationAnalyticsSummary {
  quest_id: string;
  quest_title: string;
  reason: string;
  target_capabilities: string[];
  created_at: string;
}

export interface EmployeeAnalytics {
  employee_id: string;
  full_name: string;
  department_id: string | null;
  department_name: string | null;
  role_title: string | null;
  capabilities: EmployeeCapabilityAnalyticsSummary[];
  development_areas: string[];
  recent_quest_activity: EmployeeQuestActivityAnalyticsItem[];
  latest_recommendation: EmployeeRecommendationAnalyticsSummary | null;
}

export interface CapabilityEmployeeItem {
  employee_id: string;
  full_name: string;
  department_name: string | null;
  role_title: string | null;
  level: CapabilityLevel;
  evidence_count: number;
}

export interface CapabilityEmployeesResponse {
  capability_id: string;
  capability_key: string;
  capability_name: string;
  category: CapabilityGapCategory;
  department_id: string | null;
  employees: CapabilityEmployeeItem[];
}

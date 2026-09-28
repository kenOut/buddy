from app.schemas.common import ORMBase

# Phase 8E — the API-level status contract, deliberately distinct from
# both WorkspaceAccessGrant.status (a DB value) and employee readiness
# (a Phase 8D-only concept this schema must never leak). GRANTED/PENDING/
# FAILED map 1:1 from an existing grant row's status (REVOKED — currently
# unreachable, nothing in the system revokes a grant yet — also maps to
# FAILED, so this mapping stays total over every DB status value without
# inventing employee-facing meaning for a state nothing can produce).
# NOT_CONFIGURED is the one API-only value with no DB counterpart: it
# covers every case where no grant exists to report on at all (no
# department, no active WorkspaceIntegration for the department, or an
# integration exists but no grant has been created yet) — deliberately
# a single bucket, because distinguishing those would require exposing
# whether the employee is "ready," which this contract must never do.
WORKSPACE_ACCESS_API_STATUSES = ["GRANTED", "PENDING", "FAILED", "NOT_CONFIGURED"]


class EmployeeWorkspaceAccess(ORMBase):
    """The only workspace-access shape ever safe to return to an
    employee-facing endpoint (Phase 8A security boundary, §G). Composed
    manually from a WorkspaceAccessGrant + its WorkspaceIntegration — not
    a direct ORM passthrough of either model — specifically so fields
    like `external_ref`, `provider`, `provider_ref`, `last_error`, and
    `attempt_count` can never leak here by accident of column order or a
    careless `model_validate`.

    `workspace_name` is `None` only for NOT_CONFIGURED with no
    WorkspaceIntegration at all (nothing to name yet); whenever an
    integration exists — even with no grant, or a non-GRANTED grant —
    its real `display_name` is returned, since the name itself is not
    sensitive (see EmployeeWorkspaceAccess's field list: only
    `external_ref`/provider/grant-internals are excluded, never the
    department-facing name a manager chose). `workspace_link` is
    populated only when `status == "GRANTED"`.
    """

    status: str
    workspace_name: str | None
    workspace_link: str | None = None

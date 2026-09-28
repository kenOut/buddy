"""Static, server-side-only investigation-mission content.

Follows the same trust boundary as assessment_questions.py: the evidence
shown to the employee is public, the answer key (`correct_service`,
`correct_cause`) never leaves this module.

Keyed by mission title rather than mission_id, since seeded mission ids are
randomly generated at insert time and aren't stable across reseeds.
"""

from dataclasses import dataclass, field

MISSION_SCENARIOS: dict[str, dict] = {
    "Diagnose the checkout latency spike": {
        "briefing": (
            "Customers are reporting slow checkouts on Atlas. p95 latency has "
            "tripled in the last 20 minutes. Figure out what's going on before "
            "this becomes a bigger incident."
        ),
        "evidence": {
            "metrics": [
                {
                    "id": "m1",
                    "label": "checkout-service p95 latency",
                    "detail": "420ms baseline -> 2,150ms over the last 18 minutes, rising steadily.",
                },
                {
                    "id": "m2",
                    "label": "checkout-service CPU",
                    "detail": "Flat at 22% — no CPU pressure.",
                },
                {
                    "id": "m3",
                    "label": "payments-service p95 latency",
                    "detail": "Flat at 180ms — unaffected.",
                },
                {
                    "id": "m4",
                    "label": "checkout-db connection pool utilization",
                    "detail": "Climbed from 40% to 98% in the same window.",
                },
            ],
            "logs": [
                {
                    "id": "l1",
                    "label": "checkout-service",
                    "detail": "Repeated 'QueuePool limit exceeded' warnings starting ~18 minutes ago.",
                },
                {
                    "id": "l2",
                    "label": "checkout-db",
                    "detail": "No errors. Query latency normal for the queries that do complete.",
                },
                {
                    "id": "l3",
                    "label": "inventory-service",
                    "detail": "Clean — no related errors in this window.",
                },
            ],
            "services": [
                {
                    "id": "s1",
                    "label": "checkout-service",
                    "detail": "Handles cart totals and order creation. Depends on checkout-db and payments-service.",
                },
                {
                    "id": "s2",
                    "label": "payments-service",
                    "detail": "Processes card charges. Independently healthy right now.",
                },
                {
                    "id": "s3",
                    "label": "inventory-service",
                    "detail": "Reserves stock at checkout time. Independently healthy right now.",
                },
                {
                    "id": "s4",
                    "label": "checkout-db",
                    "detail": "Primary Postgres instance backing checkout-service. Connection pool near saturation.",
                },
            ],
            "timeline": [
                {
                    "id": "t1",
                    "time": "14:02",
                    "label": "Deploy: checkout-service v2.14.0 shipped — added an order-history query on checkout page load.",
                },
                {
                    "id": "t2",
                    "time": "14:04",
                    "label": "checkout-db connection pool utilization begins climbing.",
                },
                {
                    "id": "t3",
                    "time": "14:11",
                    "label": "First 'QueuePool limit exceeded' warning logged.",
                },
                {
                    "id": "t4",
                    "time": "14:18",
                    "label": "Customer-facing checkout latency alert fires.",
                },
            ],
        },
        "service_options": ["checkout-service", "payments-service", "inventory-service", "checkout-db"],
        "cause_options": [
            "New deploy introduced a query that exhausts the DB connection pool",
            "Payments provider outage",
            "Inventory service running out of stock",
            "CPU exhaustion on checkout-service",
        ],
        "correct_service": "checkout-service",
        "correct_cause": "New deploy introduced a query that exhausts the DB connection pool",
    },
    "Investigate the payment-worker crash loop": {
        "briefing": (
            "payment-worker pods have been restarting every few minutes since this "
            "morning's deploy. Nothing is customer-facing yet, but each restart drops "
            "in-flight jobs. Find the affected service and the root cause before it does."
        ),
        "evidence": {
            "metrics": [
                {
                    "id": "m1",
                    "label": "payment-worker pod restart count",
                    "detail": "0 restarts/hr baseline -> 14 restarts/hr since 09:02.",
                },
                {
                    "id": "m2",
                    "label": "payment-worker memory usage (per pod)",
                    "detail": "Climbs from 180MB to the 512MB limit within ~3 minutes of each restart, then resets.",
                },
                {
                    "id": "m3",
                    "label": "payment-worker CPU",
                    "detail": "Flat at 12% — no CPU pressure.",
                },
                {
                    "id": "m4",
                    "label": "notification-service latency",
                    "detail": "Flat, unaffected.",
                },
            ],
            "logs": [
                {
                    "id": "l1",
                    "label": "payment-worker",
                    "detail": "'OOMKilled' in the pod termination reason on every restart since 09:02.",
                },
                {
                    "id": "l2",
                    "label": "payment-worker-db",
                    "detail": "No errors. Connections closing cleanly on each pod restart.",
                },
                {
                    "id": "l3",
                    "label": "notification-service",
                    "detail": "Clean — no related errors in this window.",
                },
            ],
            "services": [
                {
                    "id": "s1",
                    "label": "payment-worker",
                    "detail": "Background job processor for outbound payment batches. Deployed at 09:00 with an updated PDF-receipt library.",
                },
                {
                    "id": "s2",
                    "label": "notification-service",
                    "detail": "Sends payment confirmation emails/SMS. Independently healthy right now.",
                },
                {
                    "id": "s3",
                    "label": "payment-worker-db",
                    "detail": "Postgres instance backing payment-worker's job queue. No signs of stress.",
                },
                {
                    "id": "s4",
                    "label": "api-gateway",
                    "detail": "Routes external traffic. Not in the path of this background worker at all.",
                },
            ],
            "timeline": [
                {
                    "id": "t1",
                    "time": "09:00",
                    "label": "Deploy: payment-worker v4.7.0 shipped — swapped in a new PDF-receipt rendering library, pod memory limit left unchanged at 512MB.",
                },
                {
                    "id": "t2",
                    "time": "09:02",
                    "label": "First OOMKilled restart recorded.",
                },
                {
                    "id": "t3",
                    "time": "09:05",
                    "label": "Restart pattern becomes regular — roughly every 4 minutes.",
                },
                {
                    "id": "t4",
                    "time": "09:20",
                    "label": "On-call paged on restart-count alert (not yet customer-facing).",
                },
            ],
        },
        "service_options": ["payment-worker", "notification-service", "payment-worker-db", "api-gateway"],
        "cause_options": [
            "New deploy raised memory usage past the pod's memory limit, triggering OOMKills",
            "Database connection pool exhaustion",
            "Upstream API rate limiting",
            "Disk full on the node",
        ],
        "correct_service": "payment-worker",
        "correct_cause": "New deploy raised memory usage past the pod's memory limit, triggering OOMKills",
    },
    "Triage the failed production rollout": {
        "briefing": (
            "notifications-service v3.2 just went out. Error rate has spiked and the "
            "team is deciding whether to roll back. Figure out what's actually broken "
            "before that call gets made."
        ),
        "evidence": {
            "metrics": [
                {
                    "id": "m1",
                    "label": "notifications-service 5xx rate",
                    "detail": "0.1% baseline -> 18% within 6 minutes of the v3.2 deploy.",
                },
                {
                    "id": "m2",
                    "label": "notifications-service CPU/memory",
                    "detail": "Both flat and normal — no resource pressure.",
                },
                {
                    "id": "m3",
                    "label": "template-service p95 latency",
                    "detail": "Flat at 40ms — unaffected.",
                },
                {
                    "id": "m4",
                    "label": "queue-worker backlog depth",
                    "detail": "Growing, but only because notifications-service is failing to drain it — not itself the origin.",
                },
            ],
            "logs": [
                {
                    "id": "l1",
                    "label": "notifications-service",
                    "detail": "Repeated \"KeyError: 'template_id'\" starting right after the v3.2 deploy.",
                },
                {
                    "id": "l2",
                    "label": "template-service",
                    "detail": "No errors. Responding normally to every request it receives.",
                },
                {
                    "id": "l3",
                    "label": "queue-worker",
                    "detail": "No errors of its own — just a growing backlog of unprocessed messages.",
                },
            ],
            "services": [
                {
                    "id": "s1",
                    "label": "notifications-service",
                    "detail": "Consumes queued notification jobs and renders them via template-service. v3.2 deployed 6 minutes before the spike.",
                },
                {
                    "id": "s2",
                    "label": "template-service",
                    "detail": "Renders notification templates. Independently healthy right now.",
                },
                {
                    "id": "s3",
                    "label": "queue-worker",
                    "detail": "Feeds the notification queue. Independently healthy right now.",
                },
                {
                    "id": "s4",
                    "label": "auth-service",
                    "detail": "Not in this request path at all — unrelated to notification delivery.",
                },
            ],
            "timeline": [
                {
                    "id": "t1",
                    "time": "11:40",
                    "label": "Deploy: notifications-service v3.2 shipped — renamed the payload field `template_id` to `templateId` without a compatibility shim.",
                },
                {
                    "id": "t2",
                    "time": "11:41",
                    "label": "Messages already sitting in the queue (still using the old field name) start failing to process.",
                },
                {
                    "id": "t3",
                    "time": "11:46",
                    "label": "5xx alert fires on notifications-service.",
                },
                {
                    "id": "t4",
                    "time": "11:50",
                    "label": "Team opens a rollback discussion.",
                },
            ],
        },
        "service_options": ["notifications-service", "template-service", "queue-worker", "auth-service"],
        "cause_options": [
            "v3.2 deploy shipped a breaking payload field rename incompatible with already-queued messages",
            "Template service outage",
            "Auth service token expiry",
            "Queue worker running out of memory",
        ],
        "correct_service": "notifications-service",
        "correct_cause": (
            "v3.2 deploy shipped a breaking payload field rename incompatible with already-queued messages"
        ),
    },
}


def get_scenario(mission_title: str) -> dict | None:
    return MISSION_SCENARIOS.get(mission_title)


@dataclass
class GradeResult:
    """Everything the deterministic grader actually observed — the
    capability evidence pipeline (Stage 5) reads only these fields, never
    re-deriving or guessing at anything beyond what's here."""

    score: float
    passed: bool
    feedback: str
    service_correct: bool
    cause_correct: bool
    explored_widely: bool
    evidence_categories_viewed: set[str] = field(default_factory=set)


def grade(
    mission_title: str,
    affected_service: str,
    likely_cause: str,
    evidence_viewed: list[str],
) -> GradeResult:
    """Deterministic, rule-based evaluation."""
    scenario = MISSION_SCENARIOS[mission_title]

    service_correct = affected_service == scenario["correct_service"]
    cause_correct = likely_cause == scenario["correct_cause"]

    score = (50.0 if service_correct else 0.0) + (50.0 if cause_correct else 0.0)
    passed = service_correct and cause_correct

    evidence_categories_viewed = {v.split(":", 1)[0] for v in evidence_viewed if ":" in v}
    explored_widely = len(evidence_categories_viewed) >= 2

    if passed:
        feedback = (
            f"Nice work — you correctly traced this to {scenario['correct_cause'].lower()} "
            f"on {scenario['correct_service']}. That's exactly the kind of signal-following "
            "that keeps incidents short."
        )
    elif service_correct and not cause_correct:
        feedback = (
            f"You identified the right service — {scenario['correct_service']} — but the "
            "cause doesn't quite match what the evidence shows. Look again at what changed "
            "right before the symptom started."
        )
    elif cause_correct and not service_correct:
        feedback = (
            "Your reasoning about the cause is on the right track, but double-check which "
            "service is actually showing that signal in the metrics and logs."
        )
    else:
        feedback = (
            "Not quite — revisit the metrics and logs together, and look for what changed "
            "right before the symptom started."
        )

    if not explored_widely:
        feedback += " Next time, check more than one evidence source before committing to a conclusion."

    return GradeResult(
        score=score,
        passed=passed,
        feedback=feedback,
        service_correct=service_correct,
        cause_correct=cause_correct,
        explored_widely=explored_widely,
        evidence_categories_viewed=evidence_categories_viewed,
    )

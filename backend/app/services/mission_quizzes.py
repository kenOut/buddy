"""Static, server-side-only quiz content for "quiz"-workspace Missions.

Same trust boundary as mission_scenarios.py: the questions and their
options are public, the answer key (`correct_option`) never leaves this
module. Keyed by mission title for the same reason mission_scenarios.py
is — seeded mission ids aren't stable across reseeds.

Deliberately no AI step for quiz missions (see mission.py's
`workspace_type` docstring): a multiple-choice comprehension check has
an objectively right answer, so grading it is exactly the deterministic
job DETERMINISTIC Quest criteria already do — there's no qualitative
judgment left for the mock AI provider to add on top.
"""

from dataclasses import dataclass, field

MISSION_QUIZZES: dict[str, dict] = {
    "Read the on-call handbook": {
        "briefing": (
            "A quick check that the on-call handbook actually stuck — three questions "
            "on escalation, severity, and what happens when an incident starts."
        ),
        "questions": [
            {
                "id": "q1",
                "prompt": "You're paged for an alert you don't recognize. What's the first thing the handbook says to do?",
                "options": [
                    "Acknowledge the page and start reading the runbook linked in the alert",
                    "Wait for a teammate to confirm it's real before doing anything",
                    "Restart the affected service immediately",
                    "Close the page and check again in 10 minutes",
                ],
                "correct_option": "Acknowledge the page and start reading the runbook linked in the alert",
            },
            {
                "id": "q2",
                "prompt": "What separates a Sev-1 from a Sev-3 incident in the handbook's severity scale?",
                "options": [
                    "Sev-1 is customer-facing and actively losing money or data; Sev-3 is degraded but contained",
                    "Sev-1 just means more people are online to look at it",
                    "There's no real difference, it's just a label",
                    "Sev-1 is any bug found by QA before release",
                ],
                "correct_option": "Sev-1 is customer-facing and actively losing money or data; Sev-3 is degraded but contained",
            },
            {
                "id": "q3",
                "prompt": "When should you escalate to the secondary on-call, per the handbook?",
                "options": [
                    "If you haven't made progress within the escalation window, or the incident is outside your area",
                    "Never — escalating means you failed",
                    "Only if the primary on-call is on vacation",
                    "Immediately, for every single page, regardless of severity",
                ],
                "correct_option": "If you haven't made progress within the escalation window, or the incident is outside your area",
            },
        ],
    },
    "Complete security & compliance training": {
        "briefing": (
            "A short check on the security and data-handling training — three questions on "
            "phishing, customer data, and access requests."
        ),
        "questions": [
            {
                "id": "q1",
                "prompt": "You get an email asking you to reset your password via an unfamiliar link. What does the training say to do?",
                "options": [
                    "Don't click it — report it to security and reset your password directly through the known internal portal",
                    "Click it to see if it's real",
                    "Forward it to a coworker to check first",
                    "Ignore it, it'll go away",
                ],
                "correct_option": "Don't click it — report it to security and reset your password directly through the known internal portal",
            },
            {
                "id": "q2",
                "prompt": "Per the training, where is customer financial data allowed to be stored or copied to?",
                "options": [
                    "Only in approved, access-controlled systems — never in personal notes, spreadsheets, or chat messages",
                    "Anywhere convenient, as long as you delete it later",
                    "A personal cloud drive is fine if it's password-protected",
                    "It can be pasted into a support ticket for reference",
                ],
                "correct_option": "Only in approved, access-controlled systems — never in personal notes, spreadsheets, or chat messages",
            },
            {
                "id": "q3",
                "prompt": "A teammate asks you to share your system access so they can finish a task faster. What's the compliant response?",
                "options": [
                    "Direct them to request their own access through the proper approval process",
                    "Share your password since you trust them",
                    "Let them use your already-logged-in session",
                    "Do the task for them instead, no questions asked",
                ],
                "correct_option": "Direct them to request their own access through the proper approval process",
            },
        ],
    },
}


def get_quiz(mission_title: str) -> dict | None:
    return MISSION_QUIZZES.get(mission_title)


@dataclass
class QuizGradeResult:
    score: float
    passed: bool
    feedback: str
    correct_count: int
    total: int
    incorrect_question_ids: list[str] = field(default_factory=list)


def grade(mission_title: str, answers: dict[str, str]) -> QuizGradeResult:
    """Deterministic, rule-based — every question must be answered
    correctly to pass (matches how investigation missions require both
    the service AND the cause; a compliance/comprehension check with a
    partial-credit pass bar would be a strange thing to ship)."""
    quiz = MISSION_QUIZZES[mission_title]
    questions = quiz["questions"]
    total = len(questions)

    incorrect_ids = [
        q["id"] for q in questions if answers.get(q["id"]) != q["correct_option"]
    ]
    correct_count = total - len(incorrect_ids)
    score = round((correct_count / total) * 100, 2) if total else 0.0
    passed = correct_count == total

    if passed:
        feedback = "All correct — nice work, that's a solid grasp of the material."
    elif correct_count > 0:
        feedback = (
            f"{correct_count} of {total} correct. Revisit the material for the "
            f"question{'s' if len(incorrect_ids) != 1 else ''} you missed and try again."
        )
    else:
        feedback = "None correct yet — worth another pass through the material before retrying."

    return QuizGradeResult(
        score=score,
        passed=passed,
        feedback=feedback,
        correct_count=correct_count,
        total=total,
        incorrect_question_ids=incorrect_ids,
    )

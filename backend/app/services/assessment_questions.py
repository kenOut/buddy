"""Static placeholder assessment content — no AI generation yet.

Each question's first option is treated as the correct answer for scoring.
"""

ASSESSMENT_QUESTIONS: list[dict] = [
    {
        "id": "q1",
        "prompt": "Who should you page first for a production incident during your on-call rotation?",
        "options": [
            {"id": "a", "label": "The on-call runbook's designated escalation contact"},
            {"id": "b", "label": "The CEO"},
            {"id": "c", "label": "Nobody, just fix it silently"},
            {"id": "d", "label": "Wait until the next standup"},
        ],
    },
    {
        "id": "q2",
        "prompt": "Where do you find your team's deployment and rollback procedure?",
        "options": [
            {"id": "a", "label": "The team's internal runbook / wiki"},
            {"id": "b", "label": "Guessing from memory"},
            {"id": "c", "label": "Asking a random Slack channel"},
            {"id": "d", "label": "It doesn't exist"},
        ],
    },
    {
        "id": "q3",
        "prompt": "What's the first thing to check when a service's error rate spikes?",
        "options": [
            {"id": "a", "label": "Recent deploys and monitoring dashboards"},
            {"id": "b", "label": "Restart everything immediately"},
            {"id": "c", "label": "Ignore it, it'll resolve itself"},
            {"id": "d", "label": "Change the alert threshold"},
        ],
    },
    {
        "id": "q4",
        "prompt": "Who is your direct reporting line for day-to-day work?",
        "options": [
            {"id": "a", "label": "Your assigned manager"},
            {"id": "b", "label": "Whoever is online"},
            {"id": "c", "label": "No one in particular"},
            {"id": "d", "label": "The whole company"},
        ],
    },
]

_CORRECT_ANSWERS = {q["id"]: q["options"][0]["id"] for q in ASSESSMENT_QUESTIONS}


def grade(answers: dict[str, str]) -> tuple[float, bool]:
    total = len(_CORRECT_ANSWERS)
    correct = sum(1 for qid, ans in _CORRECT_ANSWERS.items() if answers.get(qid) == ans)
    score = round((correct / total) * 100, 2) if total else 0.0
    passed = score >= 75
    return score, passed

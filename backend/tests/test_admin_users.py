"""Manager Portal stakeholder accounts (AdminUser) — a second way to
obtain the same admin session the original shared ADMIN_PASSWORD
already grants (admin_auth.py, unchanged and still covered by
test_admin_auth.py). Covers: password hashing correctness, account
creation (role validation, duplicate-email conflict, password never
echoed back), per-user login (success/wrong-password/unknown-email/
deactivated), and that a stakeholder session has the exact same access
as the root admin login.

Runs against its own isolated SQLite file, per this project's convention.
"""

import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_admin_users.db"
TEST_DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

import itertools  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.password_hashing import hash_password, verify_password  # noqa: E402
from app.main import app  # noqa: E402

_email_counter = itertools.count()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/api/v1/admin/login", json={"password": get_settings().admin_password})
        yield c
    TEST_DB_PATH.unlink(missing_ok=True)


@pytest.fixture(scope="module")
def anon_client():
    with TestClient(app) as c:
        yield c


def _new_user_payload(**overrides):
    payload = {
        "email": f"stakeholder-{next(_email_counter)}@kowri.test",
        "full_name": "Test Stakeholder",
        "password": "a-real-password-123",
        "role": "people_culture",
    }
    payload.update(overrides)
    return payload


# =====================================================================
# Password hashing
# =====================================================================


def test_hash_password_never_returns_the_plaintext():
    hashed = hash_password("correct horse battery staple")
    assert "correct horse battery staple" not in hashed


def test_hash_password_is_salted_so_identical_passwords_differ():
    a = hash_password("same-password")
    b = hash_password("same-password")
    assert a != b


def test_verify_password_accepts_the_correct_password():
    hashed = hash_password("my-real-password")
    assert verify_password("my-real-password", hashed) is True


def test_verify_password_rejects_the_wrong_password():
    hashed = hash_password("my-real-password")
    assert verify_password("a-different-password", hashed) is False


def test_verify_password_rejects_a_malformed_stored_value_without_raising():
    assert verify_password("anything", "not-a-real-hash-format") is False
    assert verify_password("anything", "") is False


# =====================================================================
# Creating an AdminUser
# =====================================================================


def test_create_admin_user_requires_admin_session(anon_client):
    res = anon_client.post("/api/v1/admin/users", json=_new_user_payload())
    assert res.status_code == 401


def test_create_admin_user_succeeds(client):
    payload = _new_user_payload(full_name="Amara HR", role="people_culture")
    res = client.post("/api/v1/admin/users", json=payload)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["email"] == payload["email"]
    assert body["full_name"] == "Amara HR"
    assert body["role"] == "people_culture"
    assert body["is_active"] is True
    assert "password" not in body
    assert "password_hash" not in body


def test_create_admin_user_rejects_invalid_role(client):
    res = client.post("/api/v1/admin/users", json=_new_user_payload(role="ceo"))
    assert res.status_code == 422


def test_create_admin_user_accepts_all_three_roles(client):
    for role in ("people_culture", "security_it", "departments"):
        res = client.post("/api/v1/admin/users", json=_new_user_payload(role=role))
        assert res.status_code == 201, res.text
        assert res.json()["role"] == role


def test_create_admin_user_rejects_duplicate_email(client):
    payload = _new_user_payload()
    first = client.post("/api/v1/admin/users", json=payload)
    assert first.status_code == 201

    second = client.post("/api/v1/admin/users", json=payload)
    assert second.status_code == 409


def test_create_admin_user_rejects_short_password(client):
    res = client.post("/api/v1/admin/users", json=_new_user_payload(password="short"))
    assert res.status_code == 422


def test_list_admin_users_requires_admin_session(anon_client):
    res = anon_client.get("/api/v1/admin/users")
    assert res.status_code == 401


def test_list_admin_users_never_includes_password_hash(client):
    client.post("/api/v1/admin/users", json=_new_user_payload())
    res = client.get("/api/v1/admin/users")
    assert res.status_code == 200
    body = res.json()
    assert len(body) > 0
    for user in body:
        assert "password" not in user
        assert "password_hash" not in user


def test_user_roles_endpoint_is_public_and_lists_exactly_three_roles(anon_client):
    res = anon_client.get("/api/v1/admin/user-roles")
    assert res.status_code == 200
    assert set(res.json()) == {"people_culture", "security_it", "departments"}


# =====================================================================
# Logging in as a stakeholder account
# =====================================================================


def test_new_stakeholder_can_log_in_with_their_own_credentials(client):
    payload = _new_user_payload(password="a-unique-password-456")
    create_res = client.post("/api/v1/admin/users", json=payload)
    assert create_res.status_code == 201

    session = TestClient(app)
    login = session.post(
        "/api/v1/admin/login", json={"email": payload["email"], "password": "a-unique-password-456"}
    )
    assert login.status_code == 200, login.text
    assert login.json()["authenticated"] is True
    assert "buddy_admin_session" in login.cookies


def test_stakeholder_session_has_full_admin_access(client):
    """The explicit choice for this phase: a stakeholder account's
    session is indistinguishable in permissions from the root shared-
    password login — same cookie, same require_admin_session check."""
    payload = _new_user_payload(password="a-unique-password-789")
    client.post("/api/v1/admin/users", json=payload)

    session = TestClient(app)
    session.post("/api/v1/admin/login", json={"email": payload["email"], "password": "a-unique-password-789"})

    overview = session.get("/api/v1/admin/overview")
    assert overview.status_code == 200, overview.text

    another_user = session.post("/api/v1/admin/users", json=_new_user_payload())
    assert another_user.status_code == 201, another_user.text


def test_login_with_wrong_password_for_a_real_email_rejected(client):
    payload = _new_user_payload()
    client.post("/api/v1/admin/users", json=payload)

    session = TestClient(app)
    res = session.post("/api/v1/admin/login", json={"email": payload["email"], "password": "wrong-password"})
    assert res.status_code == 401


def test_login_with_unknown_email_rejected_with_the_same_generic_message(client):
    known_wrong = client.post(
        "/api/v1/admin/login",
        json={"email": "definitely-not-registered@kowri.test", "password": "whatever"},
    )
    assert known_wrong.status_code == 401
    assert known_wrong.json()["detail"] == "Incorrect email or password"


def test_original_shared_password_login_still_works_unchanged(anon_client):
    """Regression: adding per-user accounts must not touch the existing
    root login path at all."""
    res = anon_client.post("/api/v1/admin/login", json={"password": get_settings().admin_password})
    assert res.status_code == 200
    assert res.json()["authenticated"] is True


def test_deactivated_admin_user_cannot_log_in(client):
    """No API to deactivate an account exists yet (out of this phase's
    scope) — exercised directly at the service/ORM layer, proving
    authenticate_admin_user's is_active check actually works."""
    import asyncio

    from app.db.session import AsyncSessionLocal
    from app.services import admin_user_service
    from app.schemas.admin_user import AdminUserCreate

    payload = _new_user_payload(password="a-password-for-deactivation")

    async def _create_and_deactivate():
        async with AsyncSessionLocal() as db:
            admin_user = await admin_user_service.create_admin_user(
                db,
                AdminUserCreate(
                    email=payload["email"],
                    full_name=payload["full_name"],
                    password=payload["password"],
                    role=payload["role"],
                ),
            )
            admin_user.is_active = False
            await db.commit()

    asyncio.run(_create_and_deactivate())

    session = TestClient(app)
    res = session.post(
        "/api/v1/admin/login", json={"email": payload["email"], "password": "a-password-for-deactivation"}
    )
    assert res.status_code == 401

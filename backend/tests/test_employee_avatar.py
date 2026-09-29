"""Backend tests for POST /employees/{id}/avatar — the real upload path
behind "Meet your team"'s photos (and the admin employee detail page's
"Upload photo" control), replacing the plain initials-only chips.

Runs against its own isolated SQLite file, same convention as the other
test_*.py modules. Uploaded files land in the real app/static/avatars/
directory (not test-DB-isolated — there's nowhere else for a real file
upload to go), so this file removes anything it wrote in its own
teardown rather than leaving stray test artifacts on disk.
"""

import itertools
import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_employee_avatar.db"
TEST_DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402

AVATAR_DIR = Path(__file__).resolve().parent.parent / "app" / "static" / "avatars"
_email_counter = itertools.count()

# A minimal valid 1x1 PNG (real image bytes, not just a text stand-in —
# the endpoint only checks content_type, but this keeps the fixture honest).
_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000a4944415478da6360000002000155bff69f0000000049454e44ae426082"
)


@pytest.fixture(scope="module")
def client():
    created_before = {p.name for p in AVATAR_DIR.glob("*")} if AVATAR_DIR.exists() else set()
    with TestClient(app) as c:
        c.post("/api/v1/admin/login", json={"password": get_settings().admin_password})
        yield c
    TEST_DB_PATH.unlink(missing_ok=True)
    # Remove only files this test run actually created — never touch
    # anything that predates it (real seeded/uploaded avatars).
    if AVATAR_DIR.exists():
        for path in AVATAR_DIR.glob("*"):
            if path.name not in created_before:
                path.unlink(missing_ok=True)


@pytest.fixture(scope="module")
def org_id(client):
    bundle = client.get("/api/v1/onboarding/bundle/demo").json()
    return bundle["employee"]["organization_id"]


@pytest.fixture
def employee(client, org_id):
    return client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "full_name": "Avatar Test Employee",
            "email": f"avatar-test-{next(_email_counter)}@kowri.test",
        },
    ).json()


def test_upload_avatar_sets_avatar_url(client, employee):
    res = client.post(
        f"/api/v1/employees/{employee['id']}/avatar",
        files={"file": ("photo.png", _PNG_BYTES, "image/png")},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["avatar_url"] == f"/static/avatars/{employee['id']}.png"

    # The file is actually served back out at that path.
    served = client.get(body["avatar_url"])
    assert served.status_code == 200
    assert served.headers["content-type"].startswith("image/")


def test_upload_avatar_rejects_non_image_content_type(client, employee):
    res = client.post(
        f"/api/v1/employees/{employee['id']}/avatar",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert res.status_code == 422


def test_upload_avatar_rejects_oversized_file(client, employee):
    oversized = b"\x00" * (5 * 1024 * 1024 + 1)
    res = client.post(
        f"/api/v1/employees/{employee['id']}/avatar",
        files={"file": ("big.png", oversized, "image/png")},
    )
    assert res.status_code == 413


def test_upload_avatar_404s_for_missing_employee(client):
    res = client.post(
        "/api/v1/employees/does-not-exist/avatar",
        files={"file": ("photo.png", _PNG_BYTES, "image/png")},
    )
    assert res.status_code == 404


def test_re_uploading_with_a_different_type_removes_the_old_file(client, employee):
    first = client.post(
        f"/api/v1/employees/{employee['id']}/avatar",
        files={"file": ("photo.png", _PNG_BYTES, "image/png")},
    )
    assert first.json()["avatar_url"] == f"/static/avatars/{employee['id']}.png"
    assert (AVATAR_DIR / f"{employee['id']}.png").exists()

    # A tiny valid JPEG (SOI/EOI markers only — enough for the endpoint,
    # which never decodes the image, only trusts the declared content type).
    jpeg_bytes = b"\xff\xd8\xff\xd9"
    second = client.post(
        f"/api/v1/employees/{employee['id']}/avatar",
        files={"file": ("photo.jpg", jpeg_bytes, "image/jpeg")},
    )
    assert second.json()["avatar_url"] == f"/static/avatars/{employee['id']}.jpg"

    # The old .png must not be left behind as an orphan.
    assert not (AVATAR_DIR / f"{employee['id']}.png").exists()
    assert (AVATAR_DIR / f"{employee['id']}.jpg").exists()

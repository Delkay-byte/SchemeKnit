"""Production authentication P0 regression coverage.

The production symptom was "Your session has expired. Please sign in again."
shown for a *login* attempt. Two contracts are pinned here:

* the sign-in endpoint answers 401 only for genuinely rejected credentials,
  keeps the generic detail (no account/role oracle), and never returns a token;
* a successful sign-in for an ordinary teacher and for a platform
  administrator produces a session that survives repeated authorized calls,
  and the shared session layer rejects it once revoked.

Legacy accounts whose stored email predates normalization must still resolve.
"""
import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), "..")))

from src.config import get_settings  # noqa: E402
from src.database import Base, get_db  # noqa: E402
from src.main import app  # noqa: E402
from tests.conftest import make_user  # noqa: E402

GENERIC = "Invalid email or password"


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    get_settings.cache_clear()
    from src.security import rate_limiter
    rate_limiter.reset()
    yield
    get_settings.cache_clear()
    rate_limiter.reset()


@pytest.fixture
def http(monkeypatch):
    monkeypatch.setenv("PLATFORM_ADMIN_BOOTSTRAP_SECRET", "p0-regression-secret")
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    def _override_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_db
    client = TestClient(app)
    yield client, db
    app.dependency_overrides.pop(get_db, None)
    db.close()
    engine.dispose()


def _login(client, email, password, entry):
    return client.post(
        "/api/auth/login",
        json={"email": email, "password": password, "entry": entry},
    )


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_teacher_login_session_persists_across_requests(http):
    client, db = http
    teacher = make_user(db, role="teacher", email="p0.teacher@test.com")

    login = _login(client, teacher.email, "testpass123", "teacher")
    assert login.status_code == 200
    token = login.json()["access_token"]

    for _ in range(3):
        me = client.get("/api/auth/me", headers=_auth(token))
        assert me.status_code == 200, me.text
        assert me.json()["email"] == teacher.email


def test_platform_admin_login_session_persists_and_keeps_role_boundaries(http):
    client, db = http
    admin = make_user(
        db, role="platform_admin", is_admin=True, email="p0.admin@test.com",
    )

    login = _login(client, admin.email, "testpass123", "platform_admin")
    assert login.status_code == 200
    token = login.json()["access_token"]

    for _ in range(3):
        assert client.get("/api/auth/me", headers=_auth(token)).status_code == 200
        assert client.get(
            "/api/platform-admin/dashboard", headers=_auth(token),
        ).status_code == 200

    # The admin session must not unlock the teacher-only workflow surface.
    assert client.post(
        "/api/curriculum/p0-nonexistent/approve", headers=_auth(token),
    ).status_code == 403


def test_wrong_password_returns_generic_401_not_a_session_identity(http):
    client, db = http
    teacher = make_user(db, role="teacher", email="p0.badpass@test.com")

    response = _login(client, teacher.email, "not-the-password", "teacher")
    assert response.status_code == 401
    assert response.json()["detail"] == GENERIC
    assert "access_token" not in response.json()


def test_unknown_account_returns_the_same_generic_401(http):
    client, _db = http

    response = _login(client, "p0.ghost@test.com", "not-the-password", "teacher")
    assert response.status_code == 401
    assert response.json()["detail"] == GENERIC


def test_legacy_mixed_case_stored_email_still_logs_in(http):
    client, db = http
    legacy = make_user(
        db, role="teacher", email="  P0.Legacy.Teacher@Test.COM  ",
    )

    response = _login(client, "p0.legacy.teacher@test.com", "testpass123", "teacher")
    assert response.status_code == 200, response.text
    assert response.json()["user"]["id"] == legacy.id


def test_logout_revokes_the_shared_session(http):
    client, db = http
    teacher = make_user(db, role="teacher", email="p0.logout@test.com")

    token = _login(
        client, teacher.email, "testpass123", "teacher",
    ).json()["access_token"]
    assert client.get("/api/auth/me", headers=_auth(token)).status_code == 200

    assert client.post("/api/auth/logout", headers=_auth(token)).status_code == 200
    assert client.get("/api/auth/me", headers=_auth(token)).status_code == 401

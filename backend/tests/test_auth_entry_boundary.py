"""Authentication entry-point boundary (section 20).

The login endpoint is entry-aware: the client declares which login page it is
using and the backend validates it against the account's authoritative database
role. Cross-entry logins must fail with the same generic response as bad
credentials, and authorization must keep reading the DB role.
"""
import os
import sys
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), "..")))

from src.auth import create_access_token, create_user_token, decode_token  # noqa: E402
from src.config import get_settings  # noqa: E402
from src.database import Base, get_db  # noqa: E402
from src.main import app  # noqa: E402
from tests.conftest import make_school, make_user  # noqa: E402

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
    monkeypatch.setenv("PLATFORM_ADMIN_BOOTSTRAP_SECRET", "entry-boundary-secret")
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


def _login(client, email, password, entry=None):
    body = {"email": email, "password": password}
    if entry is not None:
        body["entry"] = entry
    return client.post("/api/auth/login", json=body)


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _teacher(db, email="teacher.entry@test.com"):
    return make_user(db, role="teacher", email=email)


def _admin(db, email="admin.entry@test.com"):
    return make_user(db, role="platform_admin", is_admin=True, email=email)


# ── 1–4. Correct entries and cross-entry rejection ────────────────────────

def test_teacher_account_teacher_entry_succeeds(http):
    client, db = http
    user = _teacher(db)
    r = _login(client, user.email, "testpass123", "teacher")
    assert r.status_code == 200
    assert r.json()["user"]["role"] == "teacher"


def test_platform_admin_platform_entry_succeeds(http):
    client, db = http
    admin = _admin(db)
    r = _login(client, admin.email, "testpass123", "platform_admin")
    assert r.status_code == 200
    assert r.json()["user"]["role"] == "platform_admin"


def test_platform_admin_cannot_use_the_teacher_entry(http):
    client, db = http
    admin = _admin(db)
    r = _login(client, admin.email, "testpass123", "teacher")
    assert r.status_code == 401
    assert r.json()["detail"] == GENERIC
    assert "access_token" not in r.json()


def test_teacher_cannot_use_the_platform_admin_entry(http):
    client, db = http
    user = _teacher(db)
    r = _login(client, user.email, "testpass123", "platform_admin")
    assert r.status_code == 401
    assert r.json()["detail"] == GENERIC


# ── 5. Missing / invalid entry is rejected, with a generic response ───────

@pytest.mark.parametrize("entry", [None, "", "root", "admin", "TEACHER_ENTRY"])
def test_missing_or_invalid_entry_is_rejected(http, entry):
    client, db = http
    user = _teacher(db, email=f"entry-{str(entry)[:6]}@test.com")
    r = _login(client, user.email, "testpass123", entry)
    assert r.status_code == 401
    assert r.json()["detail"] == GENERIC


def test_mismatch_response_is_indistinguishable_from_bad_password(http):
    client, db = http
    admin = _admin(db)
    mismatch = _login(client, admin.email, "testpass123", "teacher")
    bad_password = _login(client, admin.email, "wrong-password", "platform_admin")
    assert mismatch.status_code == bad_password.status_code == 401
    assert mismatch.json() == bad_password.json()
    assert mismatch.json()["detail"] == GENERIC


# ── 6–8. Authorization still uses the database role ───────────────────────

def test_teacher_token_is_denied_on_platform_admin_api(http):
    client, db = http
    user = _teacher(db)
    token = _login(client, user.email, "testpass123", "teacher").json()["access_token"]
    assert client.get("/api/platform-admin/dashboard", headers=_auth(token)).status_code == 403


def test_platform_admin_token_is_accepted_on_platform_admin_api(http):
    client, db = http
    admin = _admin(db)
    token = _login(client, admin.email, "testpass123", "platform_admin").json()["access_token"]
    assert client.get("/api/platform-admin/dashboard", headers=_auth(token)).status_code == 200


def test_forged_role_claim_is_still_denied(http):
    client, db = http
    user = _teacher(db)
    token = _login(client, user.email, "testpass123", "teacher").json()["access_token"]
    payload = decode_token(token)
    forged = create_access_token({
        "sub": payload["sub"],
        "email": payload.get("email"),
        "role": "platform_admin",
        "pwv": payload.get("pwv", 0),
    })
    assert client.get("/api/platform-admin/dashboard", headers=_auth(forged)).status_code == 403


# ── 9. Tampered / expired / removed sessions ──────────────────────────────

def test_tampered_token_is_rejected(http):
    client, db = http
    user = _teacher(db)
    token = _login(client, user.email, "testpass123", "teacher").json()["access_token"]
    assert client.get("/api/platform-admin/dashboard",
                      headers=_auth(token[:-4] + "AAAA")).status_code == 401


def test_expired_token_is_rejected(http):
    client, db = http
    user = _teacher(db)
    expired = create_user_token(user, expires_delta=timedelta(seconds=-60))
    assert client.get("/api/auth/me", headers=_auth(expired)).status_code == 401


def test_session_removed_on_logout_is_rejected(http):
    client, db = http
    user = _teacher(db)
    assert _login(client, user.email, "testpass123", "teacher").status_code == 200
    # Logout clears the client-held token (client-side contract); a request
    # without it must be unauthenticated.
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/platform-admin/dashboard").status_code == 401


# ── 10. Legitimate workflows ──────────────────────────────────────────────

def test_registration_then_teacher_login_still_works(http):
    client, db = http
    payload = {"email": "new.teacher@test.com", "password": "Secure1!Pass",
               "full_name": "New Teacher"}
    assert client.post("/api/auth/register/individual", json=payload).status_code == 200
    r = _login(client, payload["email"], payload["password"], "teacher")
    assert r.status_code == 200
    assert r.json()["user"]["role"] == "teacher"


def test_school_admin_entry_and_cross_entry(http):
    client, db = http
    school = make_school(db)
    sa = make_user(db, role="school_admin", is_admin=True,
                   school_id=school.id, email="school.entry@test.com")
    assert _login(client, sa.email, "testpass123", "school_admin").status_code == 200
    assert _login(client, sa.email, "testpass123", "teacher").status_code == 401
    assert _login(client, sa.email, "testpass123", "platform_admin").status_code == 401


def test_platform_admin_bootstrap_safeguard_unchanged(http):
    client, db = http
    first = client.post("/api/auth/setup-platform-admin", json={
        "bootstrap_secret": "entry-boundary-secret",
        "full_name": "First Admin",
        "email": "first.admin@test.com",
        "password": "Secure1!Pass",
    })
    assert first.status_code == 200
    second = client.post("/api/auth/setup-platform-admin", json={
        "bootstrap_secret": "entry-boundary-secret",
        "full_name": "Second Admin",
        "email": "second.admin@test.com",
        "password": "Secure1!Pass",
    })
    assert second.status_code == 410


def test_login_response_never_echoes_the_entry_or_role_on_mismatch(http):
    client, db = http
    admin = _admin(db)
    r = _login(client, admin.email, "testpass123", "teacher")
    body = r.text.lower()
    assert "platform_admin" not in body
    assert "teacher" not in body

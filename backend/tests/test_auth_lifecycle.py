"""
SchemeKnit Authentication Lifecycle Tests.

Covers the full milestone: platform-admin bootstrap, self-service password
change, admin-initiated token-based reset, session invalidation, security
boundaries, and regression of existing flows.

All tests go through the real FastAPI TestClient (real HTTP round trips).
"""

import os
import sys
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.auth import hash_password, create_user_token
from src.config import get_settings
from src.database import (
    Base, get_db, generate_id, User, PasswordResetTokenDB,
    PlatformAuditLogDB,
)
from src.main import app
from tests.conftest import make_school, make_user

BOOTSTRAP_SECRET = "test-bootstrap-secret-12345"


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    """Clear the lru_cache on get_settings so monkeypatched env vars apply,
    and reset the in-memory rate limiter so tests don't trip each other's limits."""
    get_settings.cache_clear()
    from src.security import rate_limiter
    rate_limiter.reset()
    yield
    get_settings.cache_clear()
    rate_limiter.reset()


@pytest.fixture
def http(tmp_path, monkeypatch):
    """TestClient with a shared in-memory SQLite + a configured bootstrap secret.

    Yields (client, db_session) so tests can create fixtures in the SAME
    database the HTTP client actually reads from.
    """
    monkeypatch.setenv("PLATFORM_ADMIN_BOOTSTRAP_SECRET", BOOTSTRAP_SECRET)

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


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _login(client, email, password):
    return client.post("/api/auth/login", json={"email": email, "password": password})


# ══════════════════════════════════════════════════════════════════════════════
# PLATFORM ADMIN BOOTSTRAP
# ══════════════════════════════════════════════════════════════════════════════


class TestPlatformAdminBootstrap:

    def test_status_open_when_no_admin(self, http):
        client, _ = http
        res = client.get("/api/auth/setup-platform-admin/status")
        assert res.status_code == 200
        assert res.json()["bootstrap_required"] is True

    def test_first_setup_succeeds(self, http):
        client, _ = http
        res = client.post("/api/auth/setup-platform-admin", json={
            "bootstrap_secret": BOOTSTRAP_SECRET,
            "full_name": "First Admin",
            "email": "admin@bloomcore.com",
            "password": "Secure1!Pass",
        })
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["user"]["role"] == "platform_admin"
        assert data["user"]["email"] == "admin@bloomcore.com"
        assert data["access_token"]

    def test_setup_closes_after_first_admin(self, http):
        client, _ = http
        client.post("/api/auth/setup-platform-admin", json={
            "bootstrap_secret": BOOTSTRAP_SECRET,
            "full_name": "First Admin",
            "email": "admin@bloomcore.com",
            "password": "Secure1!Pass",
        })
        res = client.get("/api/auth/setup-platform-admin/status")
        assert res.json()["bootstrap_required"] is False

        res = client.post("/api/auth/setup-platform-admin", json={
            "bootstrap_secret": BOOTSTRAP_SECRET,
            "full_name": "Second Admin",
            "email": "admin2@bloomcore.com",
            "password": "Secure1!Pass",
        })
        assert res.status_code == 410

    def test_wrong_bootstrap_secret_fails(self, http):
        client, _ = http
        res = client.post("/api/auth/setup-platform-admin", json={
            "bootstrap_secret": "WRONG-SECRET",
            "full_name": "First Admin",
            "email": "admin@bloomcore.com",
            "password": "Secure1!Pass",
        })
        assert res.status_code == 403
        # No admin created.
        res = client.get("/api/auth/setup-platform-admin/status")
        assert res.json()["bootstrap_required"] is True

    def test_empty_secret_when_not_configured(self, http, monkeypatch):
        client, _ = http
        monkeypatch.setenv("PLATFORM_ADMIN_BOOTSTRAP_SECRET", "")
        get_settings.cache_clear()
        res = client.post("/api/auth/setup-platform-admin", json={
            "bootstrap_secret": "",
            "full_name": "First Admin",
            "email": "admin@bloomcore.com",
            "password": "Secure1!Pass",
        })
        assert res.status_code == 404

    def test_invalid_password_rejected(self, http):
        client, _ = http
        res = client.post("/api/auth/setup-platform-admin", json={
            "bootstrap_secret": BOOTSTRAP_SECRET,
            "full_name": "First Admin",
            "email": "admin@bloomcore.com",
            "password": "weakpassword",
        })
        assert res.status_code == 422

    def test_invalid_email_rejected(self, http):
        client, _ = http
        res = client.post("/api/auth/setup-platform-admin", json={
            "bootstrap_secret": BOOTSTRAP_SECRET,
            "full_name": "First Admin",
            "email": "not-an-email",
            "password": "Secure1!Pass",
        })
        assert res.status_code == 422

    def test_duplicate_email_rejected(self, http):
        client, db = http
        make_user(db, email="admin@bloomcore.com")
        res = client.post("/api/auth/setup-platform-admin", json={
            "bootstrap_secret": BOOTSTRAP_SECRET,
            "full_name": "First Admin",
            "email": "admin@bloomcore.com",
            "password": "Secure1!Pass",
        })
        assert res.status_code == 409

    def test_bootstrap_admin_can_login(self, http):
        client, _ = http
        client.post("/api/auth/setup-platform-admin", json={
            "bootstrap_secret": BOOTSTRAP_SECRET,
            "full_name": "First Admin",
            "email": "admin@bloomcore.com",
            "password": "Secure1!Pass",
        })
        res = _login(client, "admin@bloomcore.com", "Secure1!Pass")
        assert res.status_code == 200
        assert res.json()["user"]["role"] == "platform_admin"

    def test_audit_log_written(self, http):
        client, _ = http
        client.post("/api/auth/setup-platform-admin", json={
            "bootstrap_secret": BOOTSTRAP_SECRET,
            "full_name": "First Admin",
            "email": "admin@bloomcore.com",
            "password": "Secure1!Pass",
        })
        login_data = _login(client, "admin@bloomcore.com", "Secure1!Pass").json()
        res = client.get("/api/platform-admin/audit?limit=10",
                         headers=_auth(login_data["access_token"]))
        assert res.status_code == 200
        actions = [l["action"] for l in res.json().get("logs", [])]
        assert "platform_admin_created" in actions


# ══════════════════════════════════════════════════════════════════════════════
# PASSWORD CHANGE (self-service, all roles)
# ══════════════════════════════════════════════════════════════════════════════


class TestPasswordChange:

    def test_teacher_changes_own_password(self, http):
        client, db = http
        user = make_user(db, role="teacher", email="teacher@test.com")
        token = create_user_token(user)

        res = client.post("/api/auth/change-password",
                          json={"current_password": "testpass123", "new_password": "NewPass456!"},
                          headers=_auth(token))
        assert res.status_code == 200, res.text
        assert res.json()["access_token"]

        # Old password fails at login.
        assert _login(client, user.email, "testpass123").status_code == 401
        # New password works.
        assert _login(client, user.email, "NewPass456!").status_code == 200

    def test_wrong_current_password_rejected(self, http):
        client, db = http
        user = make_user(db, role="teacher", email="t@test.com")
        token = create_user_token(user)
        res = client.post("/api/auth/change-password",
                          json={"current_password": "WRONG", "new_password": "NewPass456!"},
                          headers=_auth(token))
        assert res.status_code == 401

    def test_weak_new_password_rejected(self, http):
        client, db = http
        user = make_user(db, role="teacher", email="t@test.com")
        token = create_user_token(user)
        res = client.post("/api/auth/change-password",
                          json={"current_password": "testpass123", "new_password": "weak"},
                          headers=_auth(token))
        assert res.status_code == 422

    def test_same_password_rejected(self, http):
        client, db = http
        user = make_user(db, role="teacher", email="t@test.com")
        token = create_user_token(user)
        res = client.post("/api/auth/change-password",
                          json={"current_password": "testpass123", "new_password": "testpass123"},
                          headers=_auth(token))
        assert res.status_code == 422

    def test_school_admin_changes_own_password(self, http):
        client, db = http
        user = make_user(db, role="school_admin", is_admin=True, email="sa@test.com")
        token = create_user_token(user)
        res = client.post("/api/auth/change-password",
                          json={"current_password": "testpass123", "new_password": "NewPass789!"},
                          headers=_auth(token))
        assert res.status_code == 200

    def test_platform_admin_changes_own_password(self, http):
        client, db = http
        user = make_user(db, role="platform_admin", is_admin=True, email="pa@test.com")
        token = create_user_token(user)
        res = client.post("/api/auth/change-password",
                          json={"current_password": "testpass123", "new_password": "NewPass789!"},
                          headers=_auth(token))
        assert res.status_code == 200

    def test_session_invalidated_after_change(self, http):
        """Old token must stop working after a password change."""
        client, db = http
        user = make_user(db, role="teacher", email="sess@test.com")
        old_token = create_user_token(user)

        res = client.post("/api/auth/change-password",
                          json={"current_password": "testpass123", "new_password": "NewPass456!"},
                          headers=_auth(old_token))
        assert res.status_code == 200

        # The OLD token is now rejected (pwv mismatch).
        res = client.get("/api/auth/me", headers=_auth(old_token))
        assert res.status_code == 401

        # Login with new password yields a working token.
        login = _login(client, user.email, "NewPass456!").json()
        res = client.get("/api/auth/me", headers=_auth(login["access_token"]))
        assert res.status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN-INITIATED TOKEN-BASED RESET
# ══════════════════════════════════════════════════════════════════════════════


class TestAdminInitiatedReset:

    def test_platform_admin_resets_school_admin(self, http):
        client, db = http
        pa = make_user(db, role="platform_admin", is_admin=True, email="pa@test.com")
        pa_token = create_user_token(pa)
        school = make_school(db)
        sa = make_user(db, role="school_admin", is_admin=True,
                       school_id=school.id, email="sa@test.com")

        res = client.post(f"/api/auth/users/{sa.id}/initiate-reset",
                          headers=_auth(pa_token))
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["reset_token"]
        assert data["target_email"] == "sa@test.com"

        res = client.post("/api/auth/confirm-password-reset", json={
            "reset_token": data["reset_token"], "new_password": "ResetPass123!"})
        assert res.status_code == 200

        assert _login(client, "sa@test.com", "ResetPass123!").status_code == 200

    def test_platform_admin_resets_individual_teacher(self, http):
        client, db = http
        pa = make_user(db, role="platform_admin", is_admin=True, email="pa@test.com")
        pa_token = create_user_token(pa)
        teacher = make_user(db, role="teacher", school_id=None, email="indiv@test.com")

        res = client.post(f"/api/auth/users/{teacher.id}/initiate-reset",
                          headers=_auth(pa_token))
        assert res.status_code == 200
        raw = res.json()["reset_token"]

        res = client.post("/api/auth/confirm-password-reset", json={
            "reset_token": raw, "new_password": "ResetPass456!"})
        assert res.status_code == 200

        # Account is otherwise unchanged.
        login = _login(client, "indiv@test.com", "ResetPass456!")
        assert login.status_code == 200
        user_data = login.json()["user"]
        assert user_data["school_id"] is None
        assert user_data["role"] == "teacher"

    def test_platform_admin_resets_school_teacher(self, http):
        client, db = http
        pa = make_user(db, role="platform_admin", is_admin=True, email="pa@test.com")
        pa_token = create_user_token(pa)
        school = make_school(db)
        teacher = make_user(db, role="teacher", school_id=school.id, email="st@test.com")

        res = client.post(f"/api/auth/users/{teacher.id}/initiate-reset",
                          headers=_auth(pa_token))
        assert res.status_code == 200
        raw = res.json()["reset_token"]

        res = client.post("/api/auth/confirm-password-reset", json={
            "reset_token": raw, "new_password": "ResetPass789!"})
        assert res.status_code == 200

    def test_second_platform_admin_resets_first(self, http):
        """Multi-admin recovery: PA-B can reset PA-A."""
        client, db = http
        pa_a = make_user(db, role="platform_admin", is_admin=True, email="pa-a@test.com")
        pa_b = make_user(db, role="platform_admin", is_admin=True, email="pa-b@test.com")
        pb_token = create_user_token(pa_b)

        res = client.post(f"/api/auth/users/{pa_a.id}/initiate-reset",
                          headers=_auth(pb_token))
        assert res.status_code == 200
        raw = res.json()["reset_token"]

        res = client.post("/api/auth/confirm-password-reset", json={
            "reset_token": raw, "new_password": "Recovered123!"})
        assert res.status_code == 200
        assert _login(client, "pa-a@test.com", "Recovered123!").status_code == 200

    def test_token_is_single_use(self, http):
        client, db = http
        pa = make_user(db, role="platform_admin", is_admin=True, email="pa@test.com")
        pa_token = create_user_token(pa)
        teacher = make_user(db, role="teacher", email="single@test.com")

        res = client.post(f"/api/auth/users/{teacher.id}/initiate-reset",
                          headers=_auth(pa_token))
        raw = res.json()["reset_token"]

        first = client.post("/api/auth/confirm-password-reset", json={
            "reset_token": raw, "new_password": "First123!Pass"})
        assert first.status_code == 200

        second = client.post("/api/auth/confirm-password-reset", json={
            "reset_token": raw, "new_password": "Second123!Pass"})
        assert second.status_code == 410

    def test_token_cannot_be_used_for_another_account(self, http):
        client, db = http
        pa = make_user(db, role="platform_admin", is_admin=True, email="pa@test.com")
        pa_token = create_user_token(pa)
        t1 = make_user(db, role="teacher", email="t1@test.com")
        t2 = make_user(db, role="teacher", email="t2@test.com")

        res = client.post(f"/api/auth/users/{t1.id}/initiate-reset",
                          headers=_auth(pa_token))
        raw = res.json()["reset_token"]

        client.post("/api/auth/confirm-password-reset", json={
            "reset_token": raw, "new_password": "Bound123!Pass"})

        # t2's original password still works (token was bound to t1).
        assert _login(client, "t2@test.com", "testpass123").status_code == 200

    def test_token_expires(self, http):
        client, db = http
        pa = make_user(db, role="platform_admin", is_admin=True, email="pa@test.com")
        pa_token = create_user_token(pa)
        teacher = make_user(db, role="teacher", email="expire@test.com")

        res = client.post(f"/api/auth/users/{teacher.id}/initiate-reset",
                          headers=_auth(pa_token))
        raw = res.json()["reset_token"]

        # Expire the token by rewinding its expiry.
        import hashlib
        h = hashlib.sha256(raw.encode()).hexdigest()
        record = db.query(PasswordResetTokenDB).filter(
            PasswordResetTokenDB.token_hash == h).first()
        assert record is not None
        record.expires_at = datetime.utcnow() - timedelta(hours=1)
        db.commit()

        res = client.post("/api/auth/confirm-password-reset", json={
            "reset_token": raw, "new_password": "Expired123!Pass"})
        assert res.status_code == 410

    def test_validate_endpoint_returns_target(self, http):
        client, db = http
        pa = make_user(db, role="platform_admin", is_admin=True, email="pa@test.com")
        pa_token = create_user_token(pa)
        teacher = make_user(db, role="teacher", email="validate@test.com")

        res = client.post(f"/api/auth/users/{teacher.id}/initiate-reset",
                          headers=_auth(pa_token))
        raw = res.json()["reset_token"]

        res = client.get("/api/auth/reset-token/validate", params={"token": raw})
        assert res.status_code == 200
        assert res.json()["email"] == "validate@test.com"

    def test_reset_invalidates_old_sessions(self, http):
        """After a reset, the user's pre-reset token must be dead."""
        client, db = http
        pa = make_user(db, role="platform_admin", is_admin=True, email="pa@test.com")
        pa_token = create_user_token(pa)
        teacher = make_user(db, role="teacher", email="oldsess@test.com")
        old_token = create_user_token(teacher)

        res = client.post(f"/api/auth/users/{teacher.id}/initiate-reset",
                          headers=_auth(pa_token))
        raw = res.json()["reset_token"]

        client.post("/api/auth/confirm-password-reset", json={
            "reset_token": raw, "new_password": "NewSess123!"})

        # Old token rejected.
        assert client.get("/api/auth/me", headers=_auth(old_token)).status_code == 401

    def test_audit_trail(self, http):
        client, db = http
        pa = make_user(db, role="platform_admin", is_admin=True, email="pa@test.com")
        pa_token = create_user_token(pa)
        teacher = make_user(db, role="teacher", email="audit@test.com")

        client.post(f"/api/auth/users/{teacher.id}/initiate-reset",
                    headers=_auth(pa_token))

        logs = db.query(PlatformAuditLogDB).filter_by(
            action="password_reset_initiated").all()
        assert len(logs) >= 1
        # No secrets in the audit details.
        import json
        for log in logs:
            details_str = json.dumps(log.details or {})
            assert "reset_token" not in details_str


# ══════════════════════════════════════════════════════════════════════════════
# SECURITY BOUNDARIES
# ══════════════════════════════════════════════════════════════════════════════


class TestSecurityBoundaries:

    def test_teacher_cannot_initiate_reset(self, http):
        client, db = http
        school = make_school(db)
        t1 = make_user(db, role="teacher", school_id=school.id, email="t1@test.com")
        t2 = make_user(db, role="teacher", school_id=school.id, email="t2@test.com")
        token = create_user_token(t1)

        res = client.post(f"/api/auth/users/{t2.id}/initiate-reset",
                          headers=_auth(token))
        assert res.status_code == 403

    def test_school_admin_cannot_reset_platform_admin(self, http):
        client, db = http
        school = make_school(db)
        sa = make_user(db, role="school_admin", is_admin=True,
                       school_id=school.id, email="sa@test.com")
        pa = make_user(db, role="platform_admin", is_admin=True, email="pa@test.com")
        token = create_user_token(sa)

        res = client.post(f"/api/auth/users/{pa.id}/initiate-reset",
                          headers=_auth(token))
        assert res.status_code == 403

    def test_school_admin_cannot_reset_other_school_teacher(self, http):
        client, db = http
        s1 = make_school(db, name="School A")
        s2 = make_school(db, name="School B")
        sa = make_user(db, role="school_admin", is_admin=True,
                       school_id=s1.id, email="sa1@test.com")
        t2 = make_user(db, role="teacher", school_id=s2.id, email="t2@test.com")
        token = create_user_token(sa)

        res = client.post(f"/api/auth/users/{t2.id}/initiate-reset",
                          headers=_auth(token))
        assert res.status_code == 403

    def test_school_admin_can_reset_own_school_teacher(self, http):
        client, db = http
        school = make_school(db)
        sa = make_user(db, role="school_admin", is_admin=True,
                       school_id=school.id, email="sa@test.com")
        t = make_user(db, role="teacher", school_id=school.id, email="t@test.com")
        token = create_user_token(sa)

        res = client.post(f"/api/auth/users/{t.id}/initiate-reset",
                          headers=_auth(token))
        assert res.status_code == 200

    def test_admin_cannot_reset_self_via_initiate(self, http):
        client, db = http
        school = make_school(db)
        sa = make_user(db, role="school_admin", is_admin=True,
                       school_id=school.id, email="sa@test.com")
        token = create_user_token(sa)

        res = client.post(f"/api/auth/users/{sa.id}/initiate-reset",
                          headers=_auth(token))
        assert res.status_code == 400

    def test_reset_token_not_guessable(self, http):
        client, _ = http
        res = client.post("/api/auth/confirm-password-reset", json={
            "reset_token": "a" * 43,
            "new_password": "Guess123!Pass",
        })
        assert res.status_code == 404

    def test_no_password_hash_in_responses(self, http):
        client, db = http
        make_user(db, role="teacher", email="hash@test.com")
        res = _login(client, "hash@test.com", "testpass123")
        assert res.status_code == 200
        assert "hashed_password" not in res.text
        assert "$2b$" not in res.text

    def test_last_platform_admin_cannot_be_deactivated(self, http):
        client, db = http
        pa = make_user(db, role="platform_admin", is_admin=True, email="pa@test.com")
        token = create_user_token(pa)

        res = client.put(f"/api/auth/users/{pa.id}/toggle-active",
                         headers=_auth(token))
        assert res.status_code in (400, 403)


# ══════════════════════════════════════════════════════════════════════════════
# REGRESSION: existing flows still work
# ══════════════════════════════════════════════════════════════════════════════


class TestRegression:

    def test_existing_login_works(self, http):
        client, db = http
        make_user(db, role="teacher", email="reg@test.com")
        assert _login(client, "reg@test.com", "testpass123").status_code == 200

    def test_existing_individual_registration_works(self, http):
        client, _ = http
        res = client.post("/api/auth/register/individual", json={
            "email": "newindiv@test.com",
            "password": "Secure1!Pass",
            "full_name": "New Individual",
        })
        assert res.status_code == 200, res.text
        assert res.json()["user"]["role"] == "teacher"
        assert res.json()["user"]["school_id"] is None

    def test_existing_school_admin_direct_reset_works(self, http):
        """The original admin direct-set reset endpoint still functions."""
        client, db = http
        school = make_school(db)
        sa = make_user(db, role="school_admin", is_admin=True,
                       school_id=school.id, email="sa@test.com")
        t = make_user(db, role="teacher", school_id=school.id, email="t@test.com")
        token = create_user_token(sa)

        res = client.post(f"/api/auth/users/{t.id}/reset-password",
                          json={"email": "", "password": "Direct123!Reset"},
                          headers=_auth(token))
        assert res.status_code == 200

        assert _login(client, "t@test.com", "Direct123!Reset").status_code == 200

    def test_setup_status_still_published(self, http):
        client, _ = http
        res = client.get("/api/auth/setup/status")
        assert res.status_code == 200
        assert "password_policy" in res.json()

    def test_health_check(self, http):
        client, _ = http
        assert client.get("/api/health").status_code == 200


class TestMaintenanceToggle:
    """Platform-admin maintenance mode control.

    Regression: set_maintenance_mode referenced an undeclared `db` and raised
    NameError (HTTP 500) *after* mutating in-memory settings, so the UI could
    never flip the toggle and desynced from the server state.
    """

    def test_toggle_on_off_roundtrip(self, http):
        client, db = http
        admin = make_user(db, role="platform_admin")
        headers = _auth(create_user_token(admin))

        res = client.get("/api/platform-admin/maintenance", headers=headers)
        assert res.status_code == 200
        assert res.json()["maintenance"]["active"] is False

        res = client.post(
            "/api/platform-admin/maintenance",
            headers=headers,
            json={"enabled": True, "message": "Under maintenance", "estimated_restore": "2 hours"},
        )
        assert res.status_code == 200, res.text
        assert res.json()["maintenance"]["active"] is True

        res = client.get("/api/platform-admin/maintenance", headers=headers)
        assert res.status_code == 200
        assert res.json()["maintenance"]["active"] is True
        assert res.json()["maintenance"]["message"] == "Under maintenance"
        assert res.json()["maintenance"]["estimated_restore"] == "2 hours"

        res = client.post(
            "/api/platform-admin/maintenance",
            headers=headers,
            json={"enabled": False},
        )
        assert res.status_code == 200, res.text
        assert res.json()["maintenance"]["active"] is False

        res = client.get("/api/platform-admin/maintenance", headers=headers)
        assert res.json()["maintenance"]["active"] is False

        actions = [
            row.action
            for row in db.query(PlatformAuditLogDB).all()
            if row.action.startswith("maintenance_mode_")
        ]
        assert "maintenance_mode_enabled" in actions
        assert "maintenance_mode_disabled" in actions

    def test_maintenance_requires_platform_admin(self, http):
        client, db = http
        teacher = make_user(db, role="teacher")
        headers = _auth(create_user_token(teacher))

        res = client.post(
            "/api/platform-admin/maintenance",
            headers=headers,
            json={"enabled": True},
        )
        assert res.status_code == 403

        res = client.get("/api/platform-admin/maintenance", headers=headers)
        assert res.status_code == 403

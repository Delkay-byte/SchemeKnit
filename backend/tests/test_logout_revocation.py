"""Server-side logout revocation (section 21).

Logout records the JWT's unique ``jti`` so the signed-out token is rejected
before its natural expiry, without affecting the same user's other sessions.
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
from src.database import Base, get_db, RevokedTokenDB  # noqa: E402
from src.main import app  # noqa: E402
from tests.conftest import make_user  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    get_settings.cache_clear()
    from src.security import rate_limiter
    rate_limiter.reset()
    yield
    get_settings.cache_clear()
    rate_limiter.reset()


@pytest.fixture
def http():
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


def _login(client, email, password, entry):
    r = client.post("/api/auth/login",
                    json={"email": email, "password": password, "entry": entry})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_teacher_logout_revokes_only_that_session(http):
    client, db = http
    user = make_user(db, role="teacher", email="logout.teacher@test.com")

    session_one = _login(client, user.email, "testpass123", "teacher")
    session_two = _login(client, user.email, "testpass123", "teacher")

    assert client.get("/api/auth/me", headers=_auth(session_one)).status_code == 200
    assert client.get("/api/auth/me", headers=_auth(session_two)).status_code == 200

    assert client.post("/api/auth/logout", headers=_auth(session_one)).status_code == 200

    revoked = client.get("/api/auth/me", headers=_auth(session_one))
    assert revoked.status_code == 401
    assert "signed out" in revoked.json()["detail"].lower()
    # The other device's session is untouched.
    assert client.get("/api/auth/me", headers=_auth(session_two)).status_code == 200


def test_platform_admin_logout_revokes_admin_api_access(http):
    client, db = http
    admin = make_user(db, role="platform_admin", is_admin=True,
                      email="logout.admin@test.com")
    token = _login(client, admin.email, "testpass123", "platform_admin")

    assert client.get("/api/platform-admin/dashboard", headers=_auth(token)).status_code == 200
    assert client.post("/api/auth/logout", headers=_auth(token)).status_code == 200
    assert client.get("/api/platform-admin/dashboard", headers=_auth(token)).status_code == 401


def test_logout_requires_authentication(http):
    client, _ = http
    assert client.post("/api/auth/logout").status_code == 401


def test_revoked_token_cannot_be_revived_by_reuse(http):
    client, db = http
    user = make_user(db, role="teacher", email="logout.replay@test.com")
    token = _login(client, user.email, "testpass123", "teacher")
    assert client.post("/api/auth/logout", headers=_auth(token)).status_code == 200
    for _ in range(3):
        assert client.get("/api/auth/me", headers=_auth(token)).status_code == 401
        assert client.post("/api/auth/logout", headers=_auth(token)).status_code == 401
    assert db.query(RevokedTokenDB).count() == 1


def test_expired_revocation_rows_are_purged(http):
    client, db = http
    user = make_user(db, role="teacher", email="logout.purge@test.com")
    db.add(RevokedTokenDB(
        jti="expired-row", user_id=user.id,
        expires_at=datetime.utcnow() - timedelta(days=2),
    ))
    db.commit()

    token = _login(client, user.email, "testpass123", "teacher")
    assert client.post("/api/auth/logout", headers=_auth(token)).status_code == 200
    assert db.query(RevokedTokenDB).filter_by(jti="expired-row").first() is None
    # The live logout row remains until its own expiry.
    assert db.query(RevokedTokenDB).count() == 1


def test_password_change_invalidation_still_applies_after_logout_mechanism(http):
    client, db = http
    user = make_user(db, role="teacher", email="logout.pwv@test.com")
    old = _login(client, user.email, "testpass123", "teacher")
    assert client.get("/api/auth/me", headers=_auth(old)).status_code == 200

    # Simulate a password change by advancing the password version.
    user.password_changed_at = datetime.utcnow() + timedelta(seconds=1)
    db.commit()
    assert client.get("/api/auth/me", headers=_auth(old)).status_code == 401


def test_legacy_token_without_jti_remains_valid_and_cannot_be_revoked(http):
    """Tokens minted before this feature have no jti; they still authenticate
    (backwards compatibility) and simply cannot be individually revoked."""
    client, db = http
    user = make_user(db, role="teacher", email="logout.legacy@test.com")
    payload = decode_token(create_user_token(user))
    legacy = create_access_token({
        k: payload[k] for k in ("sub", "email", "role", "pwv") if k in payload
    })
    assert client.get("/api/auth/me", headers=_auth(legacy)).status_code == 200
    assert client.post("/api/auth/logout", headers=_auth(legacy)).status_code == 200
    # No jti -> nothing to revoke; behaviour is unchanged until expiry.
    assert client.get("/api/auth/me", headers=_auth(legacy)).status_code == 200

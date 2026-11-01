"""Pending TOTP enrollment: idempotent setup, expiry and one-time activation."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from src.auth import require_platform_admin, require_platform_admin_unenrolled  # noqa: E402
from src.database import get_db  # noqa: E402
from src.mfa import step_at, totp  # noqa: E402
from tests.conftest import make_user  # noqa: E402


def _app(db, admin):
    from src.routers import auth as auth_router
    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api/auth")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_platform_admin] = lambda: admin
    app.dependency_overrides[require_platform_admin_unenrolled] = lambda: admin
    return app


def _admin(db, email="pending-admin@test.com"):
    return make_user(db, role="platform_admin", is_admin=True, email=email)


def test_first_setup_persists_pending_secret_not_active(db):
    admin = _admin(db)
    with TestClient(_app(db, admin)) as client:
        res = client.post("/api/auth/mfa/setup")
    assert res.status_code == 200
    db.refresh(admin)
    body = res.json()
    assert admin.mfa_enabled is False
    assert admin.mfa_secret is None
    assert admin.mfa_pending_secret == body["secret"]
    assert admin.mfa_pending_expires_at is not None
    assert body["qr_data_uri"].startswith("data:image/svg+xml;base64,")


def test_repeated_setup_reuses_the_same_pending_secret(db):
    admin = _admin(db, "pending-repeat@test.com")
    with TestClient(_app(db, admin)) as client:
        first = client.post("/api/auth/mfa/setup").json()
        second = client.post("/api/auth/mfa/setup").json()
        third = client.post("/api/auth/mfa/setup").json()
    assert first["secret"] == second["secret"] == third["secret"]
    assert first["qr_data_uri"] == second["qr_data_uri"] == third["qr_data_uri"]


def test_multiple_tabs_share_one_pending_enrollment(db):
    admin = _admin(db, "pending-tabs@test.com")
    with TestClient(_app(db, admin)) as tab_one, TestClient(_app(db, admin)) as tab_two:
        a = tab_one.post("/api/auth/mfa/setup").json()
        b = tab_two.post("/api/auth/mfa/setup").json()
    assert a["secret"] == b["secret"]
    assert a["otpauth_uri"] == b["otpauth_uri"]


def test_a_second_session_reuses_the_committed_pending_secret(db_engine, db):
    """Two independent sessions resolve to one pending enrollment."""
    admin = _admin(db, "pending-sessions@test.com")
    with TestClient(_app(db, admin)) as client:
        first = client.post("/api/auth/mfa/setup").json()

    Session = sessionmaker(bind=db_engine)
    other = Session()
    try:
        with TestClient(_app(other, other.query(type(admin)).filter_by(id=admin.id).one())) as client:
            second = client.post("/api/auth/mfa/setup").json()
    finally:
        other.close()
    assert first["secret"] == second["secret"]


def test_valid_code_activates_and_clears_pending(db):
    admin = _admin(db, "pending-activate@test.com")
    with TestClient(_app(db, admin)) as client:
        secret = client.post("/api/auth/mfa/setup").json()["secret"]
        res = client.post("/api/auth/mfa/verify-setup", json={
            "code": totp(secret, step_at() + 1)})
    db.refresh(admin)
    assert res.status_code == 200
    assert len(res.json()["recovery_codes"]) == 8
    assert admin.mfa_enabled is True
    assert admin.mfa_secret == secret
    assert admin.mfa_pending_secret is None
    assert admin.mfa_pending_expires_at is None


def test_expired_pending_secret_is_replaced_and_codes_rejected(db):
    admin = _admin(db, "pending-expired@test.com")
    with TestClient(_app(db, admin)) as client:
        old = client.post("/api/auth/mfa/setup").json()["secret"]
        admin.mfa_pending_expires_at = datetime.utcnow() - timedelta(minutes=1)
        db.commit()

        fresh = client.post("/api/auth/mfa/setup").json()
        assert fresh["secret"] != old
        old_code = client.post("/api/auth/mfa/verify-setup", json={
            "code": totp(old, step_at() + 1)})
        assert old_code.status_code == 400
        new_code = client.post("/api/auth/mfa/verify-setup", json={
            "code": totp(fresh["secret"], step_at() + 1)})
        assert new_code.status_code == 200
    db.refresh(admin)
    assert admin.mfa_enabled is True


def test_expired_pending_without_new_setup_cannot_activate(db):
    admin = _admin(db, "pending-lapse@test.com")
    with TestClient(_app(db, admin)) as client:
        secret = client.post("/api/auth/mfa/setup").json()["secret"]
        admin.mfa_pending_expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.commit()
        res = client.post("/api/auth/mfa/verify-setup", json={
            "code": totp(secret, step_at() + 1)})
    db.refresh(admin)
    assert res.status_code == 400
    assert admin.mfa_enabled is False
    assert admin.mfa_pending_secret is None


def test_legacy_pending_secret_is_not_accepted(db):
    """Pre-upgrade rows kept an unverified secret in mfa_secret."""
    admin = _admin(db, "pending-legacy@test.com")
    admin.mfa_secret = "JBSWY3DPEHPK3PXP"
    db.commit()
    with TestClient(_app(db, admin)) as client:
        res = client.post("/api/auth/mfa/verify-setup", json={
            "code": totp("JBSWY3DPEHPK3PXP", step_at() + 1)})
        fresh = client.post("/api/auth/mfa/setup").json()
    db.refresh(admin)
    assert res.status_code == 400
    assert admin.mfa_enabled is False
    assert admin.mfa_secret is None
    assert fresh["secret"] != "JBSWY3DPEHPK3PXP"


def test_enrolled_admin_cannot_reissue_setup(db):
    admin = _admin(db, "pending-enrolled@test.com")
    with TestClient(_app(db, admin)) as client:
        secret = client.post("/api/auth/mfa/setup").json()["secret"]
        assert client.post("/api/auth/mfa/verify-setup", json={
            "code": totp(secret, step_at() + 1)}).status_code == 200
        again = client.post("/api/auth/mfa/setup")
    assert again.status_code == 400
    assert "secret" not in again.text
    assert "qr_data_uri" not in again.text

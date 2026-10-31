"""TOTP MFA enrollment, login, replay and recovery tests."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from src.auth import require_platform_admin
from src.database import get_db
from src.mfa import step_at, totp
from tests.conftest import make_user


def _app(db, admin):
    from src.routers import auth as auth_router
    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api/auth")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_platform_admin] = lambda: admin
    return app


def _login(client, email, password, **extra):
    return client.post("/api/auth/login", json={
        "email": email, "password": "testpass123",
        "entry": "platform_admin", **extra})


def test_enrollment_login_replay_and_recovery(db):
    admin = make_user(db, role="platform_admin", is_admin=True,
                      email="mfa-admin@test.com")
    app = _app(db, admin)
    with TestClient(app) as client:
        setup = client.post("/api/auth/mfa/setup")
        assert setup.status_code == 200
        secret = setup.json()["secret"]
        step = step_at()
        verify = client.post("/api/auth/mfa/verify-setup", json={
            "code": totp(secret, step + 1)})
        assert verify.status_code == 200
        codes = verify.json()["recovery_codes"]
        assert len(codes) == 8

        # Password alone is not enough once MFA is enabled.
        assert _login(client, admin.email, "testpass123").status_code == 401

        # Clear the enrollment step so the same accepted timestep can be used
        # once by the login test (the code still cannot be replayed twice).
        admin.mfa_last_step = None
        db.commit()

        # A fresh TOTP step succeeds.
        ok = _login(client, admin.email, "testpass123",
                    mfa_code=totp(secret, step + 1))
        assert ok.status_code == 200
        assert ok.json()["access_token"]

        # Replaying the same timestep is rejected.
        replay = _login(client, admin.email, "testpass123",
                        mfa_code=totp(secret, step + 1))
        assert replay.status_code == 401

        # Recovery code works once and is removed.
        recovered = _login(client, admin.email, "testpass123",
                           recovery_code=codes[0])
        assert recovered.status_code == 200
        reused = _login(client, admin.email, "testpass123",
                        recovery_code=codes[0])
        assert reused.status_code == 401


def test_disable_requires_password_and_code(db):
    admin = make_user(db, role="platform_admin", is_admin=True,
                      email="mfa-disable@test.com")
    app = _app(db, admin)
    with TestClient(app) as client:
        secret = client.post("/api/auth/mfa/setup").json()["secret"]
        step = step_at()
        assert client.post("/api/auth/mfa/verify-setup", json={
            "code": totp(secret, step + 1)}).status_code == 200
        assert client.post("/api/auth/mfa/disable", json={
            "password": "wrong", "code": totp(secret, step + 1)}).status_code == 401
        assert client.post("/api/auth/mfa/disable", json={
            "password": "testpass123", "code": totp(secret, step + 1)}).status_code == 200
        assert admin.mfa_enabled is False

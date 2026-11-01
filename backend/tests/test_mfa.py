"""TOTP MFA enrollment, login, replay and recovery tests."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from src.auth import require_platform_admin, require_platform_admin_unenrolled
from src.database import get_db
from src.mfa import step_at, totp
from tests.conftest import make_user


def _app(db, admin):
    from src.routers import auth as auth_router
    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api/auth")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_platform_admin] = lambda: admin
    app.dependency_overrides[require_platform_admin_unenrolled] = lambda: admin
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


def test_status_and_recovery_regeneration(db):
    admin = make_user(db, role="platform_admin", is_admin=True,
                      email="mfa-regen@test.com")
    app = _app(db, admin)
    with TestClient(app) as client:
        secret = client.post("/api/auth/mfa/setup").json()["secret"]
        step = step_at()
        codes = client.post("/api/auth/mfa/verify-setup", json={
            "code": totp(secret, step + 1)}).json()["recovery_codes"]
        status = client.get("/api/auth/mfa/status")
        assert status.status_code == 200
        assert status.json()["enabled"] is True
        assert status.json()["recovery_codes_remaining"] == 8
        regen = client.post("/api/auth/mfa/recovery/regenerate", json={
            "password": "testpass123", "code": totp(secret, step + 1)})
        assert regen.status_code == 200
        new_codes = regen.json()["recovery_codes"]
        assert len(new_codes) == 8
        assert new_codes != codes
        # Old recovery code no longer works.
        assert _login(client, admin.email, "testpass123",
                      recovery_code=codes[0]).status_code == 401
        assert _login(client, admin.email, "testpass123",
                      recovery_code=new_codes[0]).status_code == 200


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


# ── Enrollment surface: QR, caching, one-time secret, authorization ─────────

def test_setup_returns_local_qr_with_no_store_headers(db):
    admin = make_user(db, role="platform_admin", is_admin=True,
                      email="mfa-qr@test.com")
    app = _app(db, admin)
    with TestClient(app) as client:
        res = client.post("/api/auth/mfa/setup")
    assert res.status_code == 200
    body = res.json()
    assert body["qr_data_uri"].startswith("data:image/svg+xml;base64,")
    # The QR is generated locally from the same provisioning URI.
    assert "otpauth://totp/" in body["otpauth_uri"]
    assert "no-store" in res.headers["cache-control"]
    assert "private" in res.headers["cache-control"]
    assert res.headers["pragma"] == "no-cache"


def test_enrolled_admin_cannot_read_the_secret_again(db):
    admin = make_user(db, role="platform_admin", is_admin=True,
                      email="mfa-once@test.com")
    app = _app(db, admin)
    with TestClient(app) as client:
        secret = client.post("/api/auth/mfa/setup").json()["secret"]
        assert client.post("/api/auth/mfa/verify-setup", json={
            "code": totp(secret, step_at() + 1)}).status_code == 200
        again = client.post("/api/auth/mfa/setup")
    assert again.status_code == 400
    assert "secret" not in again.text
    assert "qr_data_uri" not in again.text


def test_invalid_and_expired_setup_codes_are_rejected(db):
    admin = make_user(db, role="platform_admin", is_admin=True,
                      email="mfa-expired@test.com")
    app = _app(db, admin)
    with TestClient(app) as client:
        secret = client.post("/api/auth/mfa/setup").json()["secret"]
        assert client.post("/api/auth/mfa/verify-setup", json={
            "code": "000000"}).status_code == 400
        assert client.post("/api/auth/mfa/verify-setup", json={
            "code": totp(secret, step_at() - 10)}).status_code == 400
        assert admin.mfa_enabled is False
        assert client.post("/api/auth/mfa/verify-setup", json={
            "code": totp(secret, step_at() + 1)}).status_code == 200
        assert admin.mfa_enabled is True


def test_non_admin_cannot_start_platform_admin_enrollment(db):
    admin = make_user(db, role="platform_admin", is_admin=True,
                      email="mfa-owner@test.com")
    teacher = make_user(db, role="teacher", email="mfa-teacher@test.com")
    from src.auth import create_user_token
    from src.database import get_db
    from fastapi import FastAPI

    from src.routers import auth as auth_router
    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api/auth")
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        denied = client.post("/api/auth/mfa/setup", headers={
            "Authorization": f"Bearer {create_user_token(teacher)}"})
        allowed = client.post("/api/auth/mfa/setup", headers={
            "Authorization": f"Bearer {create_user_token(admin)}"})
    assert denied.status_code == 403
    assert "secret" not in denied.text
    assert allowed.status_code == 200
    assert allowed.json()["secret"] != ""


def test_unenrolled_admin_is_blocked_from_console_api(db, monkeypatch):
    """Direct API calls cannot bypass enrollment when DEBUG is off."""
    from fastapi import Depends

    from src.auth import create_user_token, require_platform_admin
    from src.config import get_settings
    from src.database import get_db

    monkeypatch.setenv("DEBUG", "false")
    get_settings.cache_clear()
    monkeypatch.setattr("src.auth.settings", get_settings())

    admin = make_user(db, role="platform_admin", is_admin=True,
                      email="unenrolled-admin@test.com")
    app = FastAPI()

    @app.get("/api/platform-admin/dashboard")
    async def dashboard(user=Depends(require_platform_admin)):
        return {"ok": True}

    app.dependency_overrides[get_db] = lambda: db
    headers = {"Authorization": f"Bearer {create_user_token(admin)}"}
    with TestClient(app) as client:
        blocked = client.get("/api/platform-admin/dashboard", headers=headers)
        admin.mfa_enabled = True
        db.commit()
        allowed = client.get("/api/platform-admin/dashboard", headers=headers)
    assert blocked.status_code == 403
    assert "MFA enrollment" in blocked.json()["detail"]
    assert allowed.status_code == 200


def test_enrollment_endpoints_stay_reachable_before_mfa(db, monkeypatch):
    from src.auth import create_user_token
    from src.config import get_settings
    from src.database import get_db

    monkeypatch.setenv("DEBUG", "false")
    get_settings.cache_clear()
    monkeypatch.setattr("src.auth.settings", get_settings())

    admin = make_user(db, role="platform_admin", is_admin=True,
                      email="reachable-admin@test.com")
    from src.routers import auth as auth_router
    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api/auth")
    app.dependency_overrides[get_db] = lambda: db
    headers = {"Authorization": f"Bearer {create_user_token(admin)}"}
    with TestClient(app) as client:
        status = client.get("/api/auth/mfa/status", headers=headers)
        setup = client.post("/api/auth/mfa/setup", headers=headers)
    assert status.status_code == 200
    assert setup.status_code == 200


def test_unenrolled_admin_cannot_use_legacy_admin_routes(db, monkeypatch):
    """School-admin routes also accept platform admins; MFA gates them too."""
    from src.auth import create_user_token
    from src.config import get_settings
    from src.database import get_db

    monkeypatch.setenv("DEBUG", "false")
    get_settings.cache_clear()
    monkeypatch.setattr("src.auth.settings", get_settings())

    admin = make_user(db, role="platform_admin", is_admin=True,
                      email="legacy-admin@test.com")
    from src.routers import auth as auth_router
    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api/auth")
    app.dependency_overrides[get_db] = lambda: db
    headers = {"Authorization": f"Bearer {create_user_token(admin)}"}
    with TestClient(app) as client:
        blocked_read = client.get("/api/auth/users", headers=headers)
        blocked_write = client.post("/api/auth/users", headers=headers, json={
            "email": "created-by-unenrolled@test.com",
            "password": "StrongPass#2026",
            "full_name": "Created",
        })
        admin.mfa_enabled = True
        db.commit()
        allowed_read = client.get("/api/auth/users", headers=headers)
    assert blocked_read.status_code == 403
    assert blocked_write.status_code == 403
    assert allowed_read.status_code == 200


def test_verify_setup_cannot_reissue_codes_after_enrollment(db):
    admin = make_user(db, role="platform_admin", is_admin=True,
                      email="mfa-reissue@test.com")
    app = _app(db, admin)
    with TestClient(app) as client:
        secret = client.post("/api/auth/mfa/setup").json()["secret"]
        step = step_at()
        first = client.post("/api/auth/mfa/verify-setup", json={
            "code": totp(secret, step + 1)})
        assert first.status_code == 200
        stored = list(admin.mfa_recovery_codes)
        second = client.post("/api/auth/mfa/verify-setup", json={
            "code": totp(secret, step)})
    assert second.status_code == 400
    assert list(admin.mfa_recovery_codes) == stored

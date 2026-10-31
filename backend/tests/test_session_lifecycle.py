"""Server-verifiable session lifecycle and admin MFA gate tests."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from src import auth as auth_module
from src.auth import (
    _authenticate_user, create_user_token, create_session_record,
    hash_password, require_platform_admin, revoke_user_sessions,
)
from src.database import UserSessionDB, generate_id
from src.routers import auth as auth_router
from tests.conftest import make_user


def _login(db, user, password="Test#1234"):
    return __import__("asyncio").run(auth_router.login(
        auth_router.LoginRequest(
            email=user.email, password=password, entry="teacher"),
        db,
    ))


def test_login_creates_server_session_and_logout_revokes_it(db):
    user = make_user(db, role="teacher", email="session@test.local")
    user.hashed_password = hash_password("Test#1234")
    db.commit()
    result = _login(db, user)
    session = db.query(UserSessionDB).filter(
        UserSessionDB.user_id == user.id).one()
    assert session.revoked_at is None
    assert result["access_token"]
    assert result["mfa_enrollment_required"] is False

    token = result["access_token"]
    payload = auth_module.decode_token(token)
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    assert _authenticate_user(creds, db).id == user.id

    session.revoked_at = datetime.utcnow()
    db.commit()
    with pytest.raises(HTTPException) as exc:
        _authenticate_user(creds, db)
    assert exc.value.status_code == 401
    assert payload["jti"] == session.jti


def test_idle_timeout_rejects_session(db):
    user = make_user(db, role="teacher", email="idle@test.local")
    user.hashed_password = hash_password("Test#1234")
    db.commit()
    token = _login(db, user)["access_token"]
    session = db.query(UserSessionDB).filter(
        UserSessionDB.user_id == user.id).one()
    session.last_seen_at = datetime.utcnow() - timedelta(minutes=31)
    db.commit()
    with pytest.raises(HTTPException) as exc:
        _authenticate_user(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=token), db)
    assert exc.value.status_code == 401


def test_revoke_all_marks_every_session(db):
    user = make_user(db, role="teacher", email="all@test.local")
    create_session_record(db, user.id, generate_id())
    create_session_record(db, user.id, generate_id())
    assert revoke_user_sessions(db, user.id) >= 2
    assert db.query(UserSessionDB).filter(
        UserSessionDB.user_id == user.id,
        UserSessionDB.revoked_at.is_(None),
    ).count() == 0


@pytest.mark.asyncio
async def test_platform_admin_mutation_requires_mfa_in_production(db, monkeypatch):
    user = make_user(db, role="platform_admin", email="admin@test.local")
    token = create_user_token(user)
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    request = Request({
        "type": "http", "method": "POST", "path": "/api/platform-admin/schools",
        "headers": [], "client": ("203.0.113.5", 1234),
    })
    monkeypatch.setattr(auth_module.settings, "DEBUG", False)
    with pytest.raises(HTTPException) as exc:
        await require_platform_admin(
            credentials=creds, db=db, request=request)
    assert exc.value.status_code == 403
    assert "MFA" in str(exc.value.detail)

    user.mfa_enabled = True
    db.commit()
    assert (await require_platform_admin(
        credentials=creds, db=db, request=request)).id == user.id


@pytest.mark.asyncio
async def test_platform_admin_read_remains_available_for_enrollment(db, monkeypatch):
    user = make_user(db, role="platform_admin", email="admin-read@test.local")
    token = create_user_token(user)
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    request = Request({
        "type": "http", "method": "GET", "path": "/api/platform-admin/dashboard",
        "headers": [], "client": ("203.0.113.5", 1234),
    })
    monkeypatch.setattr(auth_module.settings, "DEBUG", False)
    assert (await require_platform_admin(
        credentials=creds, db=db, request=request)).id == user.id

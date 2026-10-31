"""Account lockout, shared rate-limit and trusted-proxy tests."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from src.auth import get_current_user
from src.database import LoginFailureDB, get_db
from src.login_security import (
    account_key, check_lockout, clear_failures, record_failure,
)
from src.security import DbRateLimiter, client_ip
from tests.conftest import make_user


def _app(db):
    from src.routers import auth as auth_router
    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api/auth")
    app.dependency_overrides[get_db] = lambda: db
    return app


def _login(client, email, password, entry="teacher"):
    return client.post("/api/auth/login", json={
        "email": email, "password": password, "entry": entry})


def test_five_failures_trigger_one_minute_cooldown(db):
    user = make_user(db, email="lockout-one@test.com")
    clear_failures(db, user.email)
    app = _app(db)
    with TestClient(app) as client:
        for _ in range(4):
            assert _login(client, user.email, "wrong-password").status_code == 401
        fifth = _login(client, user.email, "wrong-password")
        assert fifth.status_code == 429
        assert int(fifth.headers["Retry-After"]) >= 1
        assert "Too many" in fifth.json()["detail"]
        # Correct password is also blocked during cooldown.
        blocked = _login(client, user.email, "testpass123")
        assert blocked.status_code == 429
        assert "Retry-After" in blocked.headers


def test_cooldown_expiry_and_success_reset(db):
    user = make_user(db, email="lockout-expire@test.com")
    clear_failures(db, user.email)
    for _ in range(5):
        record_failure(db, user.email)
    row = db.query(LoginFailureDB).filter(
        LoginFailureDB.account_key == account_key(user.email)).one()
    row.lockout_until = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    app = _app(db)
    with TestClient(app) as client:
        assert _login(client, user.email, "testpass123").status_code == 200
    assert db.query(LoginFailureDB).filter(
        LoginFailureDB.account_key == account_key(user.email)).count() == 0


def test_lockout_escalates_to_five_then_fifteen_minutes(db):
    email = "lockout-escalate@test.com"
    clear_failures(db, email)
    base = datetime.utcnow()
    first = 0
    for i in range(5):
        first = record_failure(db, email, now=base + timedelta(seconds=i))
    assert first == 60
    row = db.query(LoginFailureDB).filter(
        LoginFailureDB.account_key == account_key(email)).one()
    row.lockout_until = base - timedelta(seconds=1)
    db.commit()
    second = 0
    for i in range(5):
        second = record_failure(
            db, email, now=base + timedelta(minutes=2, seconds=i))
    assert second == 300
    row = db.query(LoginFailureDB).filter(
        LoginFailureDB.account_key == account_key(email)).one()
    row.lockout_until = base - timedelta(seconds=1)
    db.commit()
    third = 0
    for i in range(5):
        third = record_failure(
            db, email, now=base + timedelta(minutes=10, seconds=i))
    assert third == 900


def test_account_counter_is_not_ip_scoped(db):
    email = "lockout-cross-ip@test.com"
    clear_failures(db, email)
    # The API receives no IP in these calls: the same account counter is used.
    for _ in range(4):
        assert record_failure(db, email) == 0
    assert record_failure(db, email) == 60
    assert check_lockout(db, email) > 0


def test_unknown_and_known_bad_password_are_indistinguishable(db):
    user = make_user(db, email="enum-known@test.com")
    clear_failures(db, user.email)
    clear_failures(db, "enum-unknown@test.com")
    app = _app(db)
    with TestClient(app) as client:
        known = _login(client, user.email, "wrong-password")
        unknown = _login(client, "enum-unknown@test.com", "wrong-password")
    assert known.status_code == unknown.status_code == 401
    assert known.json() == unknown.json()


def test_db_rate_limiter_is_shared_and_persistent(db_engine):
    Session = sessionmaker(bind=db_engine)
    limiter = DbRateLimiter(session_factory=Session)
    now = 1_700_000_000.0
    for i in range(20):
        allowed, _ = limiter.is_allowed(
            "203.0.113.9", "/api/auth/login", now=now + i)
        assert allowed, i
    allowed, info = limiter.is_allowed(
        "203.0.113.9", "/api/auth/login", now=now + 21)
    assert allowed is False
    assert info["limit"] == 20
    assert info["reset"] >= 1
    # A different client has an independent bucket.
    allowed, _ = limiter.is_allowed(
        "203.0.113.10", "/api/auth/login", now=now + 22)
    assert allowed is True


def test_forged_forwarded_header_is_ignored_from_untrusted_peer(monkeypatch):
    from src.config import get_settings
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "true")
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    get_settings.cache_clear()
    try:
        request = Request({
            "type": "http", "method": "GET", "path": "/",
            "headers": [(b"x-forwarded-for", b"198.51.100.7")],
            "client": ("203.0.113.5", 1234),
        })
        assert client_ip(request) == "203.0.113.5"
        trusted = Request({
            "type": "http", "method": "GET", "path": "/",
            "headers": [(b"x-forwarded-for", b"198.51.100.7, 10.1.1.1")],
            "client": ("10.1.1.1", 1234),
        })
        assert client_ip(trusted) == "198.51.100.7"
    finally:
        get_settings.cache_clear()

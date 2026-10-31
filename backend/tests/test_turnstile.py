"""Cloudflare Turnstile: server verification, replay, risk policy, CSP."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from src import turnstile  # noqa: E402
from src.config import get_settings  # noqa: E402
from src.database import TurnstileTokenDB, get_db  # noqa: E402
from src.login_security import clear_failures, record_failure  # noqa: E402
from tests.conftest import make_user  # noqa: E402

TEST_SECRET = "1x0000000000000000000000000000000AA"
TEST_SITE_KEY = "1x00000000000000000000AA"
HOST = "schemeknit-frontend.onrender.com"


def _enable(monkeypatch):
    monkeypatch.setenv("TURNSTILE_ENABLED", "true")
    monkeypatch.setenv("TURNSTILE_SECRET_KEY", TEST_SECRET)
    monkeypatch.setenv("TURNSTILE_SITE_KEY", TEST_SITE_KEY)
    monkeypatch.setenv("TURNSTILE_ALLOWED_HOSTNAMES", HOST)
    get_settings.cache_clear()


def _disable(monkeypatch):
    monkeypatch.setenv("TURNSTILE_ENABLED", "false")
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _clear_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _payload(action="register", hostname=HOST, success=True, codes=None):
    return {
        "success": success,
        "hostname": hostname,
        "action": action,
        "challenge_ts": "2026-10-31T12:00:00Z",
        "error-codes": codes or [],
    }


def _fake_siteverify(monkeypatch, payload):
    calls = []

    def fake(token, action, remote_ip):
        calls.append((token, action, remote_ip))
        return payload

    monkeypatch.setattr(turnstile, "_siteverify", fake)
    return calls


def _app(db):
    from src.routers import auth as auth_router
    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api/auth")
    app.dependency_overrides[get_db] = lambda: db
    return app


# ── Server verification core ────────────────────────────────────────────────

def test_valid_test_token_permits_the_action(db, monkeypatch):
    _enable(monkeypatch)
    _fake_siteverify(monkeypatch, _payload("register"))
    result = turnstile.verify_token(
        db, "valid-test-token", action="register")
    assert result["success"] is True
    # The documented test secret skips replay storage (test keys return the
    # same dummy token); production tokens are recorded below.
    assert db.query(TurnstileTokenDB).count() == 0


def test_missing_token_is_rejected(db, monkeypatch):
    _enable(monkeypatch)
    with pytest.raises(turnstile.TurnstileError) as exc:
        turnstile.verify_token(db, "", action="register")
    assert exc.value.status_code == 428
    assert exc.value.code == "turnstile_required"


def test_invalid_token_is_rejected(db, monkeypatch):
    _enable(monkeypatch)
    _fake_siteverify(
        monkeypatch, _payload(success=False, codes=["invalid-input-response"]))
    with pytest.raises(turnstile.TurnstileError) as exc:
        turnstile.verify_token(db, "bad", action="register")
    assert exc.value.status_code == 400
    assert exc.value.code == "turnstile_invalid"


def test_expired_token_is_rejected(db, monkeypatch):
    _enable(monkeypatch)
    _fake_siteverify(
        monkeypatch, _payload(success=False, codes=["timeout-or-duplicate"]))
    with pytest.raises(turnstile.TurnstileError) as exc:
        turnstile.verify_token(db, "expired", action="register")
    assert exc.value.status_code == 400


def test_replayed_token_is_rejected(db, monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setenv("TURNSTILE_SECRET_KEY", "production-like-secret-value")
    get_settings.cache_clear()
    _fake_siteverify(monkeypatch, _payload("register"))
    turnstile.verify_token(db, "same-token", action="register")
    with pytest.raises(turnstile.TurnstileError) as exc:
        turnstile.verify_token(db, "same-token", action="register")
    assert exc.value.code == "turnstile_replay"


def test_wrong_action_is_rejected(db, monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setenv("TURNSTILE_SECRET_KEY", "production-like-secret-value")
    get_settings.cache_clear()
    _fake_siteverify(monkeypatch, _payload("login"))
    with pytest.raises(turnstile.TurnstileError) as exc:
        turnstile.verify_token(db, "action-token", action="register")
    assert exc.value.code == "turnstile_action_mismatch"


def test_wrong_hostname_is_rejected(monkeypatch):
    monkeypatch.setenv("TURNSTILE_ENABLED", "true")
    # A non-test secret makes hostname validation authoritative.
    monkeypatch.setenv("TURNSTILE_SECRET_KEY", "production-like-secret-value")
    get_settings.cache_clear()
    with pytest.raises(turnstile.TurnstileError) as exc:
        turnstile.validate_siteverify_payload(
            _payload("register", hostname="evil.example.com"),
            expected_action="register",
            hostnames=[HOST],
        )
    assert exc.value.code == "turnstile_hostname_mismatch"


def test_siteverify_timeout_fails_closed(db, monkeypatch):
    _enable(monkeypatch)

    def boom(*args, **kwargs):
        raise TimeoutError("no siteverify")

    monkeypatch.setattr(turnstile.requests, "post", boom)
    with pytest.raises(turnstile.TurnstileError) as exc:
        turnstile.verify_token(db, "timeout-token", action="register")
    assert exc.value.status_code == 503
    assert exc.value.code == "turnstile_unavailable"


# ── HTTP entry points ───────────────────────────────────────────────────────

def test_registration_cannot_bypass_verification(db, monkeypatch):
    _enable(monkeypatch)
    with TestClient(_app(db)) as client:
        body = client.post("/api/auth/register/individual", json={
            "email": "bypass@test.com", "password": "StrongPass#2026",
            "full_name": "Bypass Test",
        })
    assert body.status_code == 428
    assert body.json()["detail"]["code"] == "turnstile_required"


def test_registration_accepts_a_verified_token(db, monkeypatch):
    _enable(monkeypatch)
    _fake_siteverify(monkeypatch, _payload("register"))
    with TestClient(_app(db)) as client:
        body = client.post("/api/auth/register/individual", json={
            "email": "verified@test.com", "password": "StrongPass#2026",
            "full_name": "Verified Teacher", "turnstile_token": "ok-token",
        })
    assert body.status_code == 200
    assert body.json()["user"]["email"] == "verified@test.com"


def test_normal_login_does_not_require_a_challenge(db, monkeypatch):
    _enable(monkeypatch)
    user = make_user(db, email="normal-login@test.com")
    clear_failures(db, user.email)
    with TestClient(_app(db)) as client:
        body = client.post("/api/auth/login", json={
            "email": user.email, "password": "testpass123",
            "entry": "teacher",
        })
    assert body.status_code == 200


def test_login_challenge_after_repeated_failures(db, monkeypatch):
    _enable(monkeypatch)
    user = make_user(db, email="risky-login@test.com")
    clear_failures(db, user.email)
    for _ in range(3):
        record_failure(db, user.email)
    with TestClient(_app(db)) as client:
        body = client.post("/api/auth/login", json={
            "email": user.email, "password": "testpass123",
            "entry": "teacher",
        })
    assert body.status_code == 428
    assert body.json()["detail"]["code"] == "turnstile_required"


def test_login_challenge_token_is_action_bound(db, monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setenv("TURNSTILE_SECRET_KEY", "production-like-secret-value")
    get_settings.cache_clear()
    user = make_user(db, email="action-login@test.com")
    clear_failures(db, user.email)
    for _ in range(3):
        record_failure(db, user.email)
    _fake_siteverify(monkeypatch, _payload("register"))
    with TestClient(_app(db)) as client:
        body = client.post("/api/auth/login", json={
            "email": user.email, "password": "testpass123",
            "entry": "teacher", "turnstile_token": "register-token",
        })
    assert body.status_code == 400
    assert body.json()["detail"]["code"] == "turnstile_action_mismatch"


def test_disabled_turnstile_keeps_local_flows_working(db, monkeypatch):
    _disable(monkeypatch)
    with TestClient(_app(db)) as client:
        body = client.post("/api/auth/register/individual", json={
            "email": "local@test.com", "password": "StrongPass#2026",
            "full_name": "Local Teacher",
        })
    assert body.status_code == 200


def test_csp_allows_only_the_required_cloudflare_origins():
    path = BACKEND.parent / "frontend" / "next.config.js"
    text = path.read_text(encoding="utf-8")
    assert "https://challenges.cloudflare.com" in text
    assert "unsafe-eval" not in text
    assert "script-src 'self' 'unsafe-inline' https://challenges.cloudflare.com" in text
    assert "frame-src 'self' https://checkout.paystack.com https://challenges.cloudflare.com" in text

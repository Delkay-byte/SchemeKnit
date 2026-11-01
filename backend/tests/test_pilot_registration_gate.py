"""Pilot registration gate: policy endpoint and end-to-end registration.

The invite code is only enforced when ``REGISTRATION_MODE=invite_only``.
Public teacher registration must stay open by default, with Turnstile and the
password policy still enforced server-side.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src import turnstile
from src.config import Settings, get_settings
from src.database import get_db
from src.routers.auth import _registration_allowed

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"

TEST_SECRET = "1x0000000000000000000000000000000AA"
TEST_SITE_KEY = "1x00000000000000000000AA"
HOST = "schemeknit-frontend.onrender.com"


@pytest.fixture(autouse=True)
def _clear_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _app(db):
    from src.routers import auth as auth_router
    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api/auth")
    app.dependency_overrides[get_db] = lambda: db
    return app


def _enable_turnstile(monkeypatch):
    monkeypatch.setenv("TURNSTILE_ENABLED", "true")
    monkeypatch.setenv("TURNSTILE_SECRET_KEY", TEST_SECRET)
    monkeypatch.setenv("TURNSTILE_SITE_KEY", TEST_SITE_KEY)
    monkeypatch.setenv("TURNSTILE_ALLOWED_HOSTNAMES", HOST)
    get_settings.cache_clear()


def _fake_siteverify(monkeypatch):
    def fake(token, action, remote_ip):
        return {
            "success": True,
            "hostname": HOST,
            "action": action,
            "challenge_ts": "2026-10-31T12:00:00Z",
            "error-codes": [],
        }

    monkeypatch.setattr(turnstile, "_siteverify", fake)


def _register(client, email, **extra):
    return client.post("/api/auth/register/individual", json={
        "email": email,
        "password": "StrongPass#2026",
        "full_name": "Public Teacher",
        "turnstile_token": "ok-token",
        **extra,
    })


# ── Pure gate rules ─────────────────────────────────────────────────────────

def test_open_mode_preserves_self_registration():
    assert _registration_allowed("open", "", "") is True
    assert _registration_allowed("OPEN", "", "anything") is True


def test_closed_mode_rejects_self_registration():
    assert _registration_allowed("closed", "secret", "secret") is False


def test_invite_only_requires_matching_code():
    assert _registration_allowed("invite_only", "pilot-123", "pilot-123") is True
    assert _registration_allowed("invite_only", "pilot-123", "wrong") is False
    assert _registration_allowed("invite_only", "pilot-123", "") is False
    assert _registration_allowed("invite_only", "", "pilot-123") is False


def test_registration_mode_is_validated():
    with pytest.raises(ValueError):
        Settings(REGISTRATION_MODE="public")


# ── Policy endpoint ─────────────────────────────────────────────────────────

def test_registration_policy_reports_open(db, monkeypatch):
    monkeypatch.setenv("REGISTRATION_MODE", "open")
    get_settings.cache_clear()
    with TestClient(_app(db)) as client:
        body = client.get("/api/auth/registration-policy")
    assert body.status_code == 200
    assert body.json() == {
        "registration_mode": "open",
        "self_registration": True,
        "invite_code_required": False,
    }
    assert "no-store" in body.headers["cache-control"]


def test_registration_policy_reports_invite_only(db, monkeypatch):
    monkeypatch.setenv("REGISTRATION_MODE", "invite_only")
    monkeypatch.setenv("PILOT_INVITE_CODE", "pilot-123")
    get_settings.cache_clear()
    with TestClient(_app(db)) as client:
        body = client.get("/api/auth/registration-policy")
    assert body.status_code == 200
    assert body.json() == {
        "registration_mode": "invite_only",
        "self_registration": True,
        "invite_code_required": True,
    }
    assert "pilot-123" not in body.text


def test_registration_policy_reports_closed(db, monkeypatch):
    monkeypatch.setenv("REGISTRATION_MODE", "closed")
    get_settings.cache_clear()
    with TestClient(_app(db)) as client:
        body = client.get("/api/auth/registration-policy")
    assert body.status_code == 200
    assert body.json()["self_registration"] is False
    assert body.json()["invite_code_required"] is False


# ── End-to-end registration ─────────────────────────────────────────────────

def test_public_registration_without_invite_code_in_open_mode(db, monkeypatch):
    monkeypatch.setenv("REGISTRATION_MODE", "open")
    _enable_turnstile(monkeypatch)
    _fake_siteverify(monkeypatch)
    with TestClient(_app(db)) as client:
        body = _register(client, "open-teacher@test.com")
    assert body.status_code == 200, body.text
    assert body.json()["user"]["email"] == "open-teacher@test.com"


def test_invite_only_rejects_missing_code_even_with_turnstile(db, monkeypatch):
    monkeypatch.setenv("REGISTRATION_MODE", "invite_only")
    monkeypatch.setenv("PILOT_INVITE_CODE", "pilot-123")
    _enable_turnstile(monkeypatch)
    _fake_siteverify(monkeypatch)
    with TestClient(_app(db)) as client:
        no_code = _register(client, "no-code@test.com")
        wrong = _register(client, "wrong-code@test.com", invite_code="nope")
        right = _register(client, "right-code@test.com", invite_code="pilot-123")
    assert no_code.status_code == 403
    assert wrong.status_code == 403
    assert right.status_code == 200, right.text


def test_invite_only_still_needs_a_turnstile_token(db, monkeypatch):
    monkeypatch.setenv("REGISTRATION_MODE", "invite_only")
    monkeypatch.setenv("PILOT_INVITE_CODE", "pilot-123")
    monkeypatch.setenv("TURNSTILE_ENABLED", "true")
    monkeypatch.setenv("TURNSTILE_SECRET_KEY", TEST_SECRET)
    monkeypatch.setenv("TURNSTILE_SITE_KEY", TEST_SITE_KEY)
    get_settings.cache_clear()
    with TestClient(_app(db)) as client:
        body = client.post("/api/auth/register/individual", json={
            "email": "no-turnstile@test.com",
            "password": "StrongPass#2026",
            "full_name": "No Challenge",
            "invite_code": "pilot-123",
        })
    assert body.status_code == 428
    assert body.json()["detail"]["code"] == "turnstile_required"


def test_open_registration_still_rejects_a_weak_password(db, monkeypatch):
    monkeypatch.setenv("REGISTRATION_MODE", "open")
    _enable_turnstile(monkeypatch)
    _fake_siteverify(monkeypatch)
    with TestClient(_app(db)) as client:
        body = client.post("/api/auth/register/individual", json={
            "email": "weak@test.com",
            "password": "short",
            "full_name": "Weak Password",
            "turnstile_token": "ok-token",
        })
    assert body.status_code == 422


# ── Frontend wiring ─────────────────────────────────────────────────────────

def test_frontend_asks_for_code_only_from_backend_policy():
    page = (FRONTEND / "src/app/signup/page.tsx").read_text(encoding="utf-8")
    api = (FRONTEND / "src/lib/api.ts").read_text(encoding="utf-8")
    env = (FRONTEND / ".env.example").read_text(encoding="utf-8")
    assert "getRegistrationPolicy" in page
    assert "getRegistrationPolicy" in api
    assert "invite_code_required" in page
    assert "policyError" in page
    assert "NEXT_PUBLIC_PILOT_INVITE_REQUIRED" in page
    assert "NEXT_PUBLIC_PILOT_INVITE_REQUIRED=false" in env
    assert "Pilot invite code" in page
    assert "invite_code: inviteCode" in api

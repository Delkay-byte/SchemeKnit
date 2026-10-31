"""Invite-only pilot registration gate (prepared, inactive by default)."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.config import Settings
from src.routers.auth import _registration_allowed

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


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


def test_frontend_asks_for_code_only_when_enabled():
    page = (FRONTEND / "src/app/signup/page.tsx").read_text(encoding="utf-8")
    api = (FRONTEND / "src/lib/api.ts").read_text(encoding="utf-8")
    env = (FRONTEND / ".env.example").read_text(encoding="utf-8")
    assert "NEXT_PUBLIC_PILOT_INVITE_REQUIRED" in page
    assert "NEXT_PUBLIC_PILOT_INVITE_REQUIRED=false" in env
    assert "Pilot invite code" in page
    assert "invite_code: inviteCode" in api

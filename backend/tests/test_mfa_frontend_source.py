"""Static contracts for the platform-admin MFA frontend."""
from __future__ import annotations

from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _text(path: str) -> str:
    return (FRONTEND / path).read_text(encoding="utf-8", errors="replace")


def test_mfa_component_and_api_wiring_exist():
    api = _text("src/lib/api.ts")
    for method in (
        "getMfaStatus", "beginMfaSetup", "verifyMfaSetup",
        "disableMfa", "regenerateMfaRecovery",
    ):
        assert method in api
    component = _text("src/components/mfa-settings-card.tsx")
    for fragment in (
        "Enable MFA", "otpauth_uri", "recovery_codes",
        "Regenerate recovery codes", "Disable MFA",
    ):
        assert fragment in component


def test_login_sends_second_factor_and_recovery_code():
    login = _text("src/components/role-login.tsx")
    assert "mfa_code" in _text("src/lib/api.ts")
    assert "recovery_code" in _text("src/lib/api.ts")
    assert "Authenticator code" in login
    assert "Recovery code" in login


def test_platform_admin_page_renders_mfa_settings():
    page = _text("src/app/(platform-admin)/platform-admin/page.tsx")
    assert "MfaSettingsCard" in page
    assert "<MfaSettingsCard" in page

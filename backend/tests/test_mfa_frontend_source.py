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
        "Enable MFA", "MfaEnrollPanel", "recovery_codes",
        "Regenerate recovery codes", "Disable MFA",
    ):
        assert fragment in component
    panel = _text("src/components/mfa-enroll-panel.tsx")
    assert "otpauth_uri" in _text("src/lib/api.ts")
    assert "qr_data_uri" in panel


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


def test_enrollment_panel_renders_qr_manual_key_and_recovery_codes():
    panel = _text("src/components/mfa-enroll-panel.tsx")
    for fragment in (
        "qr_data_uri",
        "Manual setup key",
        "recovery_codes",
        "acknowledged",
        "6-digit code",
        "Cannot be shown again",
    ):
        assert fragment in panel


def test_platform_admin_console_blocks_until_enrolled():
    page = _text("src/app/(platform-admin)/platform-admin/page.tsx")
    assert "!user.mfa_enabled" in page
    assert "MfaEnrollPanel" in page


def test_auth_context_can_refresh_the_enrolled_user():
    assert "refreshUser" in _text("src/lib/auth-context.tsx")
    page = _text("src/app/(platform-admin)/platform-admin/page.tsx")
    assert "refreshUser" in page


def test_login_explains_first_sign_in_enrollment():
    login = _text("src/components/role-login.tsx")
    assert "First sign-in?" in login
    assert "authenticator after signing in" in login


def test_settings_card_never_renders_the_secret_after_enrollment():
    card = _text("src/components/mfa-settings-card.tsx")
    # The manual key lives only inside the enrollment panel, which the card
    # renders only while MFA is not enabled.
    assert "MfaEnrollPanel" in card
    assert "status?.enabled && (" in card


def test_auth_shell_renders_exactly_one_logo():
    """One logo on every auth page, including Platform Administration."""
    shell = _text("src/components/auth/auth-shell.tsx")
    assert shell.count("<BrandCapsule") == 1


def test_cached_session_refreshes_profile_on_mount():
    ctx = _text("src/lib/auth-context.tsx")
    assert "api.getProfile()" in ctx


def test_expired_enrollment_offers_a_fresh_start():
    panel = _text("src/components/mfa-enroll-panel.tsx")
    assert "setSetup(null)" in panel
    assert "Refresh account status" in panel
    assert "onRefresh" in panel

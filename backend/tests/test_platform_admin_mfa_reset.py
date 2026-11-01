"""Operator-only Platform Admin MFA reset (CLI)."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from src.auth import create_session_record, hash_password  # noqa: E402
from src.database import PlatformAuditLogDB, UserSessionDB  # noqa: E402
from src.tools.reset_platform_admin import reset_platform_admin_mfa  # noqa: E402
from tests.conftest import make_user  # noqa: E402


def _enrolled_admin(db, email="cli-admin@test.com"):
    admin = make_user(db, role="platform_admin", is_admin=True, email=email)
    admin.hashed_password = hash_password("testpass123")
    admin.mfa_enabled = True
    admin.mfa_secret = "JBSWY3DPEHPK3PXP"
    admin.mfa_recovery_codes = ["$2b$12$notarealhash"]
    admin.mfa_last_step = 12345
    db.commit()
    create_session_record(db, admin.id, "jti-cli-one")
    create_session_record(db, admin.id, "jti-cli-two")
    return admin


def test_dry_run_changes_nothing(db):
    admin = _enrolled_admin(db)
    password_hash = admin.hashed_password
    result = reset_platform_admin_mfa(
        db, email=admin.email, operator="operator@bloomcore.com",
        reason="Lost phone", apply=False)
    db.refresh(admin)
    assert result["found"] is True
    assert result["applyable_sessions"] == 2
    assert result["applied"] is False
    assert admin.mfa_enabled is True
    assert admin.mfa_secret == "JBSWY3DPEHPK3PXP"
    assert admin.hashed_password == password_hash
    assert db.query(PlatformAuditLogDB).count() == 0


def test_apply_clears_mfa_only_revokes_sessions_and_audits(db):
    admin = _enrolled_admin(db)
    password_hash = admin.hashed_password
    result = reset_platform_admin_mfa(
        db, email=admin.email, operator="operator@bloomcore.com",
        reason="Lost phone and recovery codes", apply=True)
    db.refresh(admin)
    assert result["applied"] is True
    assert admin.mfa_enabled is False
    assert admin.mfa_secret is None
    assert admin.mfa_recovery_codes == []
    assert admin.mfa_last_step is None
    assert admin.hashed_password == password_hash
    assert admin.role == "platform_admin"
    assert admin.is_active is True
    sessions = db.query(UserSessionDB).filter(
        UserSessionDB.user_id == admin.id).all()
    assert sessions and all(s.revoked_at is not None for s in sessions)

    audit = db.query(PlatformAuditLogDB).one()
    assert audit.action == "platform_admin_mfa_reset_cli"
    assert audit.target_id == admin.id
    assert audit.details["operator"] == "operator@bloomcore.com"
    assert audit.details["reason"] == "Lost phone and recovery codes"


def test_unknown_or_non_admin_account_is_not_touched(db):
    teacher = make_user(db, role="teacher", email="teacher-not-admin@test.com")
    missing = reset_platform_admin_mfa(
        db, email="nobody@test.com", operator="op", reason="lost", apply=True)
    wrong_role = reset_platform_admin_mfa(
        db, email=teacher.email, operator="op", reason="lost", apply=True)
    assert missing["found"] is False
    assert wrong_role["found"] is False
    assert db.query(PlatformAuditLogDB).count() == 0

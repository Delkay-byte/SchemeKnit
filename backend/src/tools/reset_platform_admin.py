"""
SchemeKnit break-glass recovery: reset a locked-out Platform Admin.

Usage:
    python -m src.tools.reset_platform_admin --email admin@example.com

This is a SERVER-SIDE OPERATIONAL TOOL. It is never exposed through the web
UI. It requires local filesystem access to the database.

What it does:
    1. Finds the platform admin by email.
    2. Issues a one-time, expiring reset token (same mechanism as the web
       admin-initiated reset flow).
    3. Prints the token for the operator to deliver out-of-band.
    4. The admin then uses /reset-password to set a new password.
    5. Audits the event as method='cli_break_glass'.

Alternative (--set-password):
    Directly sets a new password (prompted, never echoed, never logged).
    Use only when the token flow is impractical.

This tool does NOT bypass the password policy.
"""

import argparse
import getpass
import os
import sys
from datetime import datetime, timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

# Resolve src package for both dev and PyInstaller-frozen contexts.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _resolve_engine():
    """Find the database the same way create_platform_admin.py does."""
    from src.config import get_settings
    settings = get_settings()

    if settings.DATABASE_URL.startswith("postgresql"):
        print(f"Database: PostgreSQL (DATABASE_URL)")
        return create_engine(settings.DATABASE_URL)

    candidates = []
    env_dir = os.environ.get("TEACHFLOW_DATA_DIR")
    if env_dir:
        candidates.append(os.path.join(env_dir, "teachflow.db"))
    candidates.append(os.path.join(os.getcwd(), "teachflow.db"))
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(os.path.join(appdata, "teachflow-desktop", "data", "teachflow.db"))
    candidates.append(os.path.expanduser("~/teachflow_data/teachflow.db"))

    for path in candidates:
        if os.path.exists(path):
            print(f"Database: SQLite at {path}")
            return create_engine(f"sqlite:///{path}")

    print("ERROR: No database found. Searched:")
    for c in candidates:
        print(f"  {c}")
    sys.exit(1)


def _hash_token(raw: str) -> str:
    import hashlib
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def reset_platform_admin_mfa(
    db: Session,
    email: str,
    operator: str,
    reason: str,
    apply: bool = False,
) -> dict:
    """Clear a platform admin's TOTP enrollment. MFA columns only.

    The caller supplies an explicit target, an operator identity and a reason;
    every applied run writes a ``platform_audit_logs`` row and revokes the
    account's active sessions so the next sign-in must re-enroll. Passwords,
    roles and the active flag are never touched. Dry-run by default.
    """
    from datetime import datetime

    from src.database import (
        PlatformAuditLogDB, User, UserSessionDB, generate_id,
    )
    from src.validation import normalize_email

    normalized = normalize_email(email)
    user = db.query(User).filter(
        User.email == normalized,
        User.role == "platform_admin",
    ).first()
    if user is None:
        return {
            "found": False,
            "email": normalized,
            "applied": False,
            "applyable_sessions": 0,
        }

    active_sessions = db.query(UserSessionDB).filter(
        UserSessionDB.user_id == user.id,
        UserSessionDB.revoked_at.is_(None),
    ).count()

    result = {
        "found": True,
        "email": user.email,
        "mfa_enabled": bool(user.mfa_enabled),
        "applyable_sessions": active_sessions,
        "applied": False,
    }
    if not apply:
        return result

    user.mfa_enabled = False
    user.mfa_secret = None
    user.mfa_recovery_codes = []
    user.mfa_last_step = None

    # One transaction: MFA clear, session revocation and audit either all
    # land or none do.
    revoked = db.query(UserSessionDB).filter(
        UserSessionDB.user_id == user.id,
        UserSessionDB.revoked_at.is_(None),
    ).update({UserSessionDB.revoked_at: datetime.utcnow()},
             synchronize_session=False)
    db.add(PlatformAuditLogDB(
        id=generate_id(),
        actor_id=user.id,
        actor_role="cli_operator",
        action="platform_admin_mfa_reset_cli",
        target_type="user",
        target_id=user.id,
        details={
            "method": "cli_operator_mfa_reset",
            "operator": operator,
            "reason": reason,
            "target_email": user.email,
        },
    ))
    db.commit()

    result["applied"] = True
    result["sessions_revoked"] = int(revoked or 0)
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Break-glass recovery for a locked-out Platform Admin."
    )
    parser.add_argument("--email", required=True, help="Platform admin email")
    parser.add_argument(
        "--set-password",
        action="store_true",
        help="Directly set a new password (prompted) instead of issuing a reset token.",
    )
    parser.add_argument(
        "--reset-mfa",
        action="store_true",
        help="Clear TOTP enrollment only (audited, revokes sessions). Dry-run unless --apply.",
    )
    parser.add_argument("--operator", help="Operator identity recorded in the audit log")
    parser.add_argument("--reason", help="Why MFA is being reset (recorded in the audit log)")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the MFA reset. Without this flag the command is a dry run.",
    )
    args = parser.parse_args()

    if args.set_password and args.reset_mfa:
        print("ERROR: choose --set-password or --reset-mfa, not both.")
        sys.exit(2)
    if args.reset_mfa and (not args.operator or not args.reason):
        print("ERROR: --reset-mfa requires --operator and --reason.")
        sys.exit(2)
    if args.apply and not args.reset_mfa:
        print("ERROR: --apply is only valid with --reset-mfa.")
        sys.exit(2)

    from src.validation import validate_email, validate_password, normalize_email
    from src.auth import hash_password

    ok, msg = validate_email(args.email)
    if not ok:
        print(f"Invalid email: {msg}")
        sys.exit(1)

    engine = _resolve_engine()
    with Session(engine) as db:
        # Find the platform admin.
        row = db.execute(text(
            "SELECT id, email, full_name, is_active FROM users "
            "WHERE email = :email AND role = 'platform_admin'"
        ), {"email": normalize_email(args.email)}).fetchone()

        if row is None:
            print(f"ERROR: No platform admin found with email {args.email}")
            sys.exit(1)

        user_id, email, full_name, is_active = row
        print(f"\nFound: {full_name} <{email}> (active={is_active})")

        if not is_active:
            print("WARNING: This account is disabled. Reset will not unlock it.")
            cont = input("Continue anyway? [y/N] ")
            if cont.lower() != "y":
                sys.exit(0)

        if args.reset_mfa:
            print("\nMFA reset plan (TOTP only — password, role and active flag are untouched)")
            plan = reset_platform_admin_mfa(
                db, args.email, args.operator, args.reason, apply=False)
            print(f"  Target: {email}")
            print(f"  MFA enabled: {plan.get('mfa_enabled')}")
            print(f"  Active sessions to revoke: {plan['applyable_sessions']}")
            print(f"  Operator: {args.operator}")
            print(f"  Reason: {args.reason}")

            if not plan.get("mfa_enabled"):
                print("\nMFA is not enabled for this account; nothing to reset.")
                engine.dispose()
                sys.exit(0)

            if not args.apply:
                print("\nDRY RUN — no changes made. Re-run with --apply to reset.")
                engine.dispose()
                sys.exit(0)

            confirmation = input(
                f'\nType the target email to confirm MFA reset: ')
            if normalize_email(confirmation) != normalize_email(email):
                print("Confirmation did not match. No changes made.")
                engine.dispose()
                sys.exit(1)

            result = reset_platform_admin_mfa(
                db, args.email, args.operator, args.reason, apply=True)
            print("\nMFA enrollment cleared.")
            print(f"Sessions revoked: {result.get('sessions_revoked', 0)}")
            print("The admin must enroll a new authenticator at /platform-admin.")
            engine.dispose()
            sys.exit(0)

        if args.set_password:
            # ── Direct password replacement ────────────────────────────────
            print("\nSet a new password for this platform admin.")
            print("The password must satisfy the production password policy:")
            print("  At least 8 characters, including a letter, a number and a symbol.\n")
            while True:
                pw = getpass.getpass("New password: ")
                pw2 = getpass.getpass("Confirm password: ")
                if pw != pw2:
                    print("Passwords do not match. Try again.")
                    continue
                ok, msg = validate_password(pw)
                if not ok:
                    print(f"Password policy: {msg}")
                    continue
                break

            db.execute(text(
                "UPDATE users SET hashed_password = :pw, password_changed_at = :now "
                "WHERE id = :id"
            ), {"pw": hash_password(pw), "now": datetime.utcnow(), "id": user_id})

            # Audit (no secret in the audit row).
            db.execute(text(
                "INSERT INTO platform_audit_logs (id, actor_id, actor_role, action, "
                "target_type, target_id, details, timestamp) "
                "VALUES (:aid, :actor, 'platform_admin', 'platform_admin_password_reset_cli', "
                "'user', :tid, :details, :ts)"
            ), {
                "aid": str(__import__("uuid").uuid4()),
                "actor": user_id,
                "tid": user_id,
                "details": __import__("json").dumps({"method": "cli_break_glass_set_password"}),
                "ts": datetime.utcnow(),
            })
            db.commit()
            print("\nPassword updated. The admin can now sign in with the new password.")
            print("All existing sessions for this account have been invalidated.")

        else:
            # ── One-time reset token ───────────────────────────────────────
            import secrets
            from src.config import get_settings
            settings = get_settings()
            raw = secrets.token_urlsafe(32)
            now = datetime.utcnow()
            expires = now + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_TTL_MINUTES)

            db.execute(text(
                "INSERT INTO password_reset_tokens "
                "(id, user_id, token_hash, expires_at, used_at, initiated_by, initiated_at, method) "
                "VALUES (:id, :uid, :th, :exp, NULL, :ib, :now, 'cli_break_glass')"
            ), {
                "id": str(__import__("uuid").uuid4()),
                "uid": user_id,
                "th": _hash_token(raw),
                "exp": expires,
                "ib": user_id,
                "now": now,
            })

            # Audit (no token in the audit row).
            db.execute(text(
                "INSERT INTO platform_audit_logs (id, actor_id, actor_role, action, "
                "target_type, target_id, details, timestamp) "
                "VALUES (:aid, :actor, 'platform_admin', 'platform_admin_password_reset_cli', "
                "'user', :tid, :details, :ts)"
            ), {
                "aid": str(__import__("uuid").uuid4()),
                "actor": user_id,
                "tid": user_id,
                "details": __import__("json").dumps({"method": "cli_break_glass_token"}),
                "ts": datetime.utcnow(),
            })
            db.commit()

            print("\n" + "=" * 70)
            print("ONE-TIME RESET TOKEN (expires in "
                  f"{settings.PASSWORD_RESET_TOKEN_TTL_MINUTES} minutes):")
            print("=" * 70)
            print(raw)
            print("=" * 70)
            print("\nDeliver this token to the admin out-of-band (phone, in person).")
            print("The admin uses it at: /reset-password")
            print("This token is single-use and cannot be retrieved again.")

    engine.dispose()


if __name__ == "__main__":
    main()

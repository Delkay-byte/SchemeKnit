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
    args = parser.parse_args()

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

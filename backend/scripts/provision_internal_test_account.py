"""Provision the ONE owner-only internal test account.

The account is an ordinary teacher account (never a Super Admin) whose
``users.is_internal_test_account`` flag grants unlimited APPLICATION-level
lesson-plan generation and AI usage. The flag is checked server-side only; no
client header, email or request field can set it.

This script never prints or changes a password, token or secret. It refuses to
create an account: register the teacher account normally (the owner controls the
inbox and sets the password through the normal activation/reset flow), then run:

    python scripts/provision_internal_test_account.py \
        --email owner@example.org --actor owner@example.org --apply

Omit ``--apply`` for a dry run. Use ``--revoke`` to remove the entitlement.

The account persists across deployments because the flag is a database column
(migration v055), not a process setting.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.database import SessionLocal, User  # noqa: E402
from src.logging_config import log_event  # noqa: E402


def _mask(email: str) -> str:
    local, _, domain = (email or "").partition("@")
    visible = local[:2] if len(local) > 2 else local[:1]
    return f"{visible}***@{domain}" if domain else "***"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True,
                        help="Existing teacher account to entitle")
    parser.add_argument("--actor", required=True,
                        help="Owner/admin identity recorded in the audit log")
    parser.add_argument("--apply", action="store_true",
                        help="Persist the change (default: dry run)")
    parser.add_argument("--revoke", action="store_true",
                        help="Remove the entitlement instead of granting it")
    args = parser.parse_args()

    email = " ".join((args.email or "").split()).strip().lower()
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            print("BLOCKED: no account exists with that email. Register the "
                  "teacher account through the normal signup/activation flow, "
                  "then re-run this script. No account or password was created.")
            return 2
        if user.is_admin or (user.role or "") in ("platform_admin", "school_admin"):
            print("BLOCKED: the internal test account must be a normal teacher "
                  "account, never an administrator. Choose the dedicated "
                  "teacher account.")
            return 3

        if args.revoke:
            targets = [user] if user.is_internal_test_account else []
        else:
            already = (db.query(User)
                       .filter(User.is_internal_test_account.is_(True),
                               User.id != user.id)
                       .all())
            if already:
                print("BLOCKED: another account already holds this entitlement "
                      f"({len(already)}). Revoke it first; exactly one internal "
                      "test account is allowed.")
                return 4
            targets = [user]

        action = "revoke" if args.revoke else "grant"
        if not args.apply:
            print(f"DRY RUN: would {action} the internal test entitlement for "
                  f"{_mask(email)} (account id {user.id}). Nothing changed.")
            return 0

        changed = 0
        for target in targets:
            if bool(target.is_internal_test_account) != (not args.revoke):
                target.is_internal_test_account = not args.revoke
                changed += 1
        db.commit()
        log_event("internal_test_account_changed", action=action,
                  actor=args.actor, account_id=user.id,
                  changed=changed, internal_test_account=not args.revoke)
        print(f"OK: {action} applied to {_mask(email)} (account id {user.id}), "
              f"changed={changed}. No password, token or secret was read or "
              "written.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

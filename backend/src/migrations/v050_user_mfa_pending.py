"""Migration v050: pending TOTP enrollment state.

Adds two nullable columns so an enrollment secret is kept separate from the
active secret and can carry an expiry. Existing enrolled administrators keep
their active secret untouched. Unverified secrets left in ``mfa_secret`` by
the pre-idempotent flow are cleared: they had no expiry and must never become
active without a fresh verified enrollment.

Additive and non-destructive to accounts, passwords, roles and lessons.
"""

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text

from ..database import engine

MIGRATION_VERSION = "v050_user_mfa_pending"
MIGRATION_NAME = "Pending TOTP enrollment secret and expiry"


def _columns(inspector, table):
    try:
        return {c["name"] for c in inspector.get_columns(table)}
    except Exception:
        return set()


def up(db):
    inspector = sa_inspect(engine)
    if not inspector.has_table("users"):
        return
    cols = _columns(inspector, "users")
    if "mfa_pending_secret" not in cols:
        db.execute(text(
            "ALTER TABLE users ADD COLUMN mfa_pending_secret VARCHAR"
        ))
    if "mfa_pending_expires_at" not in cols:
        db.execute(text(
            "ALTER TABLE users ADD COLUMN mfa_pending_expires_at TIMESTAMP"
        ))
    # Pre-upgrade unverified secrets are not enrollments under the new policy:
    # clear them so only a fresh, expiring pending secret can activate MFA.
    db.execute(text(
        "UPDATE users SET mfa_secret = NULL "
        "WHERE mfa_enabled = FALSE AND mfa_secret IS NOT NULL"
    ))
    db.commit()


def down(db):
    # Columns and security state are intentionally retained: dropping them is
    # destructive and forward-only rollback is the repository convention.
    return

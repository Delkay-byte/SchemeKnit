"""Migration v045: privileged-account MFA columns.

Additive nullable/defaulted columns only. Existing administrators remain
logged in and are not forced to enroll during deployment.
"""

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text

from ..database import engine

MIGRATION_VERSION = "v045_user_mfa"
MIGRATION_NAME = "TOTP MFA fields for privileged users"


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
    if "mfa_enabled" not in cols:
        db.execute(text(
            "ALTER TABLE users ADD COLUMN mfa_enabled BOOLEAN DEFAULT FALSE"
        ))
    if "mfa_secret" not in cols:
        db.execute(text("ALTER TABLE users ADD COLUMN mfa_secret VARCHAR"))
    if "mfa_recovery_codes" not in cols:
        # JSON is portable in SQLite; PostgreSQL also accepts JSON text here.
        db.execute(text(
            "ALTER TABLE users ADD COLUMN mfa_recovery_codes JSON DEFAULT '[]'"
        ))
    if "mfa_last_step" not in cols:
        db.execute(text("ALTER TABLE users ADD COLUMN mfa_last_step INTEGER"))
    db.commit()


def down(db):
    # Columns are intentionally retained: dropping security state is
    # destructive and forward-only rollback is the repository convention.
    return

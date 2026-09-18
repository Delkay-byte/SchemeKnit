"""
Migration v015: Password lifecycle support.

New table:
- password_reset_tokens: one-time, expiring tokens for admin-initiated
  password resets and break-glass recovery.

Updated table:
- users: add password_changed_at (session invalidation — the JWT carries a
  ``pwv`` claim that must match this value; a mismatch means the token was
  issued before the password changed and must be rejected).
"""

from datetime import datetime

from sqlalchemy import text, inspect as sa_inspect

from ..database import engine


MIGRATION_NAME = "Password lifecycle: reset tokens + session invalidation"


def up(db):
    """Apply migration."""
    inspector = sa_inspect(engine)

    # ── users.password_changed_at ─────────────────────────────────────────────
    if inspector.has_table("users"):
        cols = [c["name"] for c in inspector.get_columns("users")]
        if "password_changed_at" not in cols:
            # SQLite cannot ADD COLUMN with a non-constant default; add as
            # nullable, then backfill from created_at.
            db.execute(text("ALTER TABLE users ADD COLUMN password_changed_at TIMESTAMP"))
            db.execute(text(
                "UPDATE users SET password_changed_at = created_at "
                "WHERE password_changed_at IS NULL"
            ))

    # ── password_reset_tokens ─────────────────────────────────────────────────
    if not inspector.has_table("password_reset_tokens"):
        db.execute(text("""
            CREATE TABLE password_reset_tokens (
                id VARCHAR PRIMARY KEY,
                user_id VARCHAR NOT NULL REFERENCES users(id),
                token_hash VARCHAR NOT NULL UNIQUE,
                expires_at TIMESTAMP NOT NULL,
                used_at TIMESTAMP,
                initiated_by VARCHAR NOT NULL,
                initiated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                method VARCHAR DEFAULT 'web_admin'
            )
        """))
        db.execute(text(
            "CREATE INDEX ix_reset_token_user ON password_reset_tokens (user_id)"
        ))
        db.execute(text(
            "CREATE INDEX ix_reset_token_hash ON password_reset_tokens (token_hash)"
        ))

    db.commit()


def down(db):
    """Rollback migration."""
    inspector = sa_inspect(engine)

    if inspector.has_table("password_reset_tokens"):
        db.execute(text("DROP TABLE IF EXISTS password_reset_tokens"))

    if inspector.has_table("users"):
        cols = [c["name"] for c in inspector.get_columns("users")]
        if "password_changed_at" in cols:
            # SQLite cannot DROP COLUMN before 3.35; use the table-rebuild
            # fallback only if the version supports it.
            db.execute(text("ALTER TABLE users DROP COLUMN password_changed_at"))

    db.commit()

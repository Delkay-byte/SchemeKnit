"""Migration v044: login-failure lockout and shared rate-limit counters.

Additive tables only. No user, lesson, credit or payment row is modified.
"""

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text

from ..database import engine

MIGRATION_VERSION = "v044_security_counters"
MIGRATION_NAME = "Progressive login lockout and shared rate-limit counters"


def up(db):
    inspector = sa_inspect(engine)
    if not inspector.has_table("login_failure_counters"):
        db.execute(text(
            "CREATE TABLE login_failure_counters ("
            "id VARCHAR NOT NULL PRIMARY KEY, "
            "account_key VARCHAR NOT NULL UNIQUE, "
            "failed_count INTEGER NOT NULL DEFAULT 0, "
            "window_started_at TIMESTAMP NOT NULL, "
            "last_failed_at TIMESTAMP, "
            "lockout_count INTEGER NOT NULL DEFAULT 0, "
            "last_lockout_at TIMESTAMP, "
            "lockout_until TIMESTAMP, "
            "updated_at TIMESTAMP"
            ")"
        ))
        db.commit()
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_login_failure_until "
        "ON login_failure_counters (lockout_until)"
    ))
    if not inspector.has_table("rate_limit_counters"):
        db.execute(text(
            "CREATE TABLE rate_limit_counters ("
            "id VARCHAR NOT NULL PRIMARY KEY, "
            "bucket_key VARCHAR NOT NULL, "
            "window_start INTEGER NOT NULL, "
            "count INTEGER NOT NULL DEFAULT 0, "
            "created_at TIMESTAMP, "
            "CONSTRAINT uq_rate_limit_bucket_window "
            "UNIQUE (bucket_key, window_start)"
            ")"
        ))
        db.commit()
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_rate_limit_window "
        "ON rate_limit_counters (window_start)"
    ))
    db.commit()


def down(db):
    inspector = sa_inspect(engine)
    if inspector.has_table("rate_limit_counters"):
        db.execute(text("DROP TABLE rate_limit_counters"))
    if inspector.has_table("login_failure_counters"):
        db.execute(text("DROP TABLE login_failure_counters"))
    db.commit()

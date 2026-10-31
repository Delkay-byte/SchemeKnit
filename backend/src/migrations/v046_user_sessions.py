"""Migration v046: server-verifiable login sessions."""
from sqlalchemy import inspect as sa_inspect, text

MIGRATION_VERSION = "v046_user_sessions"
MIGRATION_NAME = "Server-verifiable login sessions"


def up(db):
    if sa_inspect(db.get_bind()).has_table("user_sessions"):
        return
    db.execute(text(
        "CREATE TABLE user_sessions ("
        "jti VARCHAR PRIMARY KEY, "
        "user_id VARCHAR NOT NULL, "
        "created_at TIMESTAMP NOT NULL, "
        "last_seen_at TIMESTAMP NOT NULL, "
        "expires_at TIMESTAMP NOT NULL, "
        "revoked_at TIMESTAMP NULL)"
    ))
    db.execute(text(
        "CREATE INDEX ix_user_sessions_user ON user_sessions (user_id, revoked_at)"
    ))
    db.execute(text(
        "CREATE INDEX ix_user_sessions_expiry ON user_sessions (expires_at)"
    ))
    db.commit()


def down(db):
    if sa_inspect(db.get_bind()).has_table("user_sessions"):
        db.execute(text("DROP TABLE user_sessions"))
        db.commit()

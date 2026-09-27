"""
Migration v029: persistent one-time download tokens.

The export download link (``GET /api/generation/downloads/{token}``) used a
process-local dict. On a multi-process deployment the POST that issues the token
and the browser's GET can reach different workers, so the token was missing and
the download 404'd. Persisting the token makes the handoff worker-agnostic while
keeping the security properties: unguessable, user-bound, short-lived, and
single-use (``used_at``).

Additive and non-destructive: creates one new table.
"""

from sqlalchemy import text, inspect as sa_inspect
from ..database import engine

MIGRATION_VERSION = "v029_download_tokens"
MIGRATION_NAME = "Persistent one-time download tokens"


def up(db):
    inspector = sa_inspect(engine)
    if inspector.has_table("download_tokens"):
        return
    db.execute(text(
        """
        CREATE TABLE download_tokens (
            token VARCHAR PRIMARY KEY,
            user_id VARCHAR NOT NULL REFERENCES users (id),
            job_id VARCHAR NOT NULL,
            path VARCHAR NOT NULL,
            media_type VARCHAR NOT NULL,
            filename VARCHAR NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            used_at TIMESTAMP,
            created_at TIMESTAMP
        )
        """
    ))
    db.execute(text(
        "CREATE INDEX ix_download_tokens_user ON download_tokens (user_id)"
    ))
    db.execute(text(
        "CREATE INDEX ix_download_tokens_expires ON download_tokens (expires_at)"
    ))
    db.commit()


def down(db):
    inspector = sa_inspect(engine)
    if inspector.has_table("download_tokens"):
        db.execute(text("DROP TABLE download_tokens"))
        db.commit()

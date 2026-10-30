"""
Migration v034: worker heartbeat for generation jobs.

Adds a nullable ``generation_jobs.heartbeat_at`` timestamp. A running worker
refreshes it while it owns the job, so stale-job reconciliation can distinguish
a healthy long run from a crashed process. Legacy rows keep NULL and fall back
to ``created_at``.

Additive and dialect-portable: ``TIMESTAMP`` is accepted by SQLite and
PostgreSQL (the v008 convention, unlike the SQLite-only ``DATETIME`` type).
"""

from sqlalchemy import text, inspect as sa_inspect
from ..database import engine

MIGRATION_VERSION = "v034_generation_job_heartbeat"
MIGRATION_NAME = "Generation job worker heartbeat"


def up(db):
    """Add generation_jobs.heartbeat_at if missing (idempotent)."""
    inspector = sa_inspect(engine)
    cols = []
    if inspector.has_table("generation_jobs"):
        cols = [c["name"] for c in inspector.get_columns("generation_jobs")]

    if "heartbeat_at" not in cols:
        db.execute(text(
            "ALTER TABLE generation_jobs ADD COLUMN heartbeat_at TIMESTAMP"
        ))
        db.commit()


def down(db):
    """Additive migrations are never rolled back."""
    pass

"""
Migration v008: Export events table for persisted workflow stage 5.

Dialect-portable (SQLite + PostgreSQL): TIMESTAMP (not DATETIME),
inspector-based existence check (not sqlite_master).
"""

from sqlalchemy import text, inspect as sa_inspect
from ..database import engine

MIGRATION_VERSION = "v008_export_events"
MIGRATION_NAME = "Export events table"


def up(db):
    """Create export_events table (CREATE TABLE IF NOT EXISTS semantics)."""
    inspector = sa_inspect(engine)
    if inspector.has_table("export_events"):
        return

    db.execute(text("""
        CREATE TABLE export_events (
            id VARCHAR PRIMARY KEY,
            job_id VARCHAR NOT NULL,
            scheme_id VARCHAR NOT NULL,
            owner_id VARCHAR NOT NULL,
            format VARCHAR NOT NULL,
            created_at TIMESTAMP
        )
    """))
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_exports_owner_scheme "
        "ON export_events (owner_id, scheme_id)"
    ))
    db.commit()


def down(db):
    """SQLite doesn't support DROP COLUMN."""
    pass

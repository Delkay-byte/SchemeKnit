"""
Migration v009: Track scheme storage filenames for safe orphan cleanup.

Dialect-portable (SQLite + PostgreSQL).
"""

from sqlalchemy import text, inspect as sa_inspect
from ..database import engine

MIGRATION_VERSION = "v009_scheme_storage_filename"
MIGRATION_NAME = "Scheme storage filename column"


def up(db):
    """Add storage_filename column to schemes."""
    inspector = sa_inspect(engine)
    cols = []
    if inspector.has_table("schemes"):
        cols = [c["name"] for c in inspector.get_columns("schemes")]

    if "storage_filename" not in cols:
        db.execute(text("ALTER TABLE schemes ADD COLUMN storage_filename VARCHAR"))
        db.commit()


def down(db):
    """SQLite doesn't support DROP COLUMN."""
    pass

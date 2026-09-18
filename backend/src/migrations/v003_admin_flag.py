"""
Migration v003: Add is_admin flag to users table.
"""

from sqlalchemy import text, inspect as sa_inspect
from ..database import engine


MIGRATION_NAME = "Add admin flag to users"


def up(db):
    """Apply migration."""
    inspector = sa_inspect(engine)
    if inspector.has_table("users"):
        cols = [c["name"] for c in inspector.get_columns("users")]
        if "is_admin" not in cols:
            db.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT FALSE"))
    db.commit()


def down(db):
    """Rollback migration."""
    db.commit()

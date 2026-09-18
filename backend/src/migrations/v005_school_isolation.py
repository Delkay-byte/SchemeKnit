"""
Migration v005: Add school_id to schemes and lesson_plans for school-level data isolation.

Dialect-portable (SQLite + PostgreSQL): uses SQLAlchemy inspection instead of PRAGMA.
"""

from sqlalchemy import text, inspect as sa_inspect
from ..database import engine


MIGRATION_VERSION = "v005_school_isolation"
MIGRATION_NAME = "Add school_id for school-level data isolation"


def _columns(db, table):
    inspector = sa_inspect(engine)
    if not inspector.has_table(table):
        return []
    return [c["name"] for c in inspector.get_columns(table)]


def up(db):
    """Add school_id column to schemes and lesson_plans tables."""
    # Add school_id to schemes
    if "school_id" not in _columns(db, "schemes"):
        db.execute(text("ALTER TABLE schemes ADD COLUMN school_id VARCHAR"))
        db.commit()

    # Backfill school_id from owner's school_id
    db.execute(text("""
        UPDATE schemes SET school_id = (
            SELECT school_id FROM users WHERE users.id = schemes.owner_id
        ) WHERE school_id IS NULL
    """))
    db.commit()

    # Add school_id to lesson_plans
    if "school_id" not in _columns(db, "lesson_plans"):
        db.execute(text("ALTER TABLE lesson_plans ADD COLUMN school_id VARCHAR"))
        db.commit()

    # Backfill school_id from owner's school_id
    db.execute(text("""
        UPDATE lesson_plans SET school_id = (
            SELECT school_id FROM users WHERE users.id = lesson_plans.owner_id
        ) WHERE school_id IS NULL
    """))
    db.commit()


def down(db):
    """Remove school_id columns (SQLite doesn't support DROP COLUMN in older versions)."""
    pass

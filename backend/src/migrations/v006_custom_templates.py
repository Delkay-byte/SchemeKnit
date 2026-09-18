"""
Migration v006: Add custom template support columns to template_definitions.

Dialect-portable (SQLite + PostgreSQL).
"""

from sqlalchemy import text, inspect as sa_inspect
from ..database import engine

MIGRATION_VERSION = "v006_custom_templates"
MIGRATION_NAME = "Add custom template columns"


def up(db):
    """Add template_file_path and is_custom columns."""
    inspector = sa_inspect(engine)
    cols = []
    if inspector.has_table("template_definitions"):
        cols = [c["name"] for c in inspector.get_columns("template_definitions")]

    if "template_file_path" not in cols:
        db.execute(text("ALTER TABLE template_definitions ADD COLUMN template_file_path VARCHAR"))
        db.commit()

    if "is_custom" not in cols:
        db.execute(text("ALTER TABLE template_definitions ADD COLUMN is_custom BOOLEAN DEFAULT FALSE"))
        db.commit()

    if "source_type" not in cols:
        db.execute(text("ALTER TABLE template_definitions ADD COLUMN source_type VARCHAR DEFAULT 'builtin'"))
        db.commit()


def down(db):
    """SQLite doesn't support DROP COLUMN."""
    pass

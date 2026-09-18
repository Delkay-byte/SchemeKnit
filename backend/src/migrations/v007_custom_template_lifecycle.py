"""
Migration v007: Custom template lifecycle columns on template_definitions.

- status: active | archived (soft-lifecycle; financial/history rows preserved)
- original_filename: teacher-visible sample document name
- structure: TemplateStructure IR JSON (tables, merges, labels, mappings)

Dialect-portable (SQLite + PostgreSQL).
"""

from sqlalchemy import text, inspect as sa_inspect
from ..database import engine

MIGRATION_VERSION = "v007_custom_template_lifecycle"
MIGRATION_NAME = "Custom template lifecycle columns"


def up(db):
    """Add status, original_filename, and structure columns."""
    inspector = sa_inspect(engine)
    cols = []
    if inspector.has_table("template_definitions"):
        cols = [c["name"] for c in inspector.get_columns("template_definitions")]

    if "status" not in cols:
        db.execute(text("ALTER TABLE template_definitions ADD COLUMN status VARCHAR DEFAULT 'active'"))
        db.commit()

    if "original_filename" not in cols:
        db.execute(text("ALTER TABLE template_definitions ADD COLUMN original_filename VARCHAR"))
        db.commit()

    if "structure" not in cols:
        db.execute(text("ALTER TABLE template_definitions ADD COLUMN structure JSON"))
        db.commit()


def down(db):
    """SQLite doesn't support DROP COLUMN."""
    pass

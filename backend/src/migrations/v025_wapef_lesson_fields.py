"""
Migration v025: WAPEF structured lesson fields.

The Approved WAPEF Plan stores four teacher-selected structured fields plus a
remarks column per lesson. Additive and dialect-portable: existing lessons
stay valid with empty defaults.
"""

from sqlalchemy import text, inspect as sa_inspect
from ..database import engine

MIGRATION_VERSION = "v025_wapef_lesson_fields"
MIGRATION_NAME = "WAPEF structured lesson fields"


def up(db):
    """Add the WAPEF lesson columns."""
    inspector = sa_inspect(engine)
    cols = []
    if inspector.has_table("lesson_plans"):
        cols = [c["name"] for c in inspector.get_columns("lesson_plans")]

    wanted = {
        "wapef_deep_hope": "TEXT DEFAULT ''",
        "wapef_storyline": "TEXT DEFAULT ''",
        "wapef_through_lines": "JSON DEFAULT '[]'",
        "wapef_gods_story": "VARCHAR DEFAULT ''",
        "remarks": "TEXT DEFAULT ''",
    }
    for col, ddl in wanted.items():
        if col not in cols:
            db.execute(text(f"ALTER TABLE lesson_plans ADD COLUMN {col} {ddl}"))
            db.commit()


def down(db):
    """SQLite doesn't support DROP COLUMN; additive migrations are never rolled back."""
    pass

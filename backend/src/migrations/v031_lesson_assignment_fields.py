"""
Migration v031: per-lesson assignment + template persistence columns.

The lesson template was recorded in the database by v001 but never wired to
the ORM, and lessons carried a single ``homework`` string with no split
between in-class work and at-home work. Additive and dialect-portable:
existing lessons stay valid with empty defaults.
"""

from sqlalchemy import text, inspect as sa_inspect
from ..database import engine

MIGRATION_VERSION = "v031_lesson_assignment_fields"
MIGRATION_NAME = "Lesson assignment and template persistence columns"


def up(db):
    """Add class_assignment, home_assignment, and template_id if missing."""
    inspector = sa_inspect(engine)
    cols = []
    if inspector.has_table("lesson_plans"):
        cols = [c["name"] for c in inspector.get_columns("lesson_plans")]

    wanted = {
        "class_assignment": "TEXT DEFAULT ''",
        "home_assignment": "TEXT DEFAULT ''",
        # v026 added these to ``weeks``; the lesson rows built FROM a
        # special-period allocation dropped them, so after save+reload the
        # review UI lost the special-period identity.
        "special_period_label": "TEXT DEFAULT ''",
        "special_period_type": "VARCHAR DEFAULT ''",
        # v001 added this on databases that existed then; guard for any
        # database created from a stale ORM snapshot.
        "template_id": "VARCHAR",
    }
    for col, ddl in wanted.items():
        if col not in cols:
            db.execute(text(f"ALTER TABLE lesson_plans ADD COLUMN {col} {ddl}"))
            db.commit()


def down(db):
    """SQLite doesn't support DROP COLUMN; additive migrations are never rolled back."""
    pass

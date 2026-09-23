"""
Migration v021: Add weeks.week_ending_derived flag.

Source week-ending dates are authoritative. When the source document omits
a date the parser derives one and must persist that fact so UI/export can
label the value DERIVED instead of presenting it as curriculum truth.
"""

from sqlalchemy import text, inspect as sa_inspect
from ..database import engine

MIGRATION_VERSION = "v021_week_ending_derived"
MIGRATION_NAME = "Add week_ending_derived flag to weeks"


def up(db):
    inspector = sa_inspect(engine)
    cols = [c["name"] for c in inspector.get_columns("weeks")]
    if "week_ending_derived" not in cols:
        db.execute(text(
            "ALTER TABLE weeks ADD COLUMN week_ending_derived BOOLEAN NOT NULL DEFAULT 0"
        ))
        db.commit()


def down(db):
    """SQLite does not support DROP COLUMN; no-op."""
    pass

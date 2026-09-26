"""
Migration v026: special-period metadata on weeks.

Non-instructional special periods (mid-term, exam, vacation, non-teaching
revision) are represented as DATA on the week row: the verbatim source label
plus the normalized period type. Additive and dialect-portable: existing weeks
stay valid with empty defaults ("" = normal instructional week).
"""

from sqlalchemy import text, inspect as sa_inspect
from ..database import engine

MIGRATION_VERSION = "v026_special_period_metadata"
MIGRATION_NAME = "Special period metadata on weeks"


def up(db):
    """Add the special-period columns to weeks."""
    inspector = sa_inspect(engine)
    cols = []
    if inspector.has_table("weeks"):
        cols = [c["name"] for c in inspector.get_columns("weeks")]

    wanted = {
        "special_period_label": "TEXT DEFAULT ''",
        "special_period_type": "VARCHAR DEFAULT ''",
    }
    for col, ddl in wanted.items():
        if col not in cols:
            db.execute(text(f"ALTER TABLE weeks ADD COLUMN {col} {ddl}"))
            db.commit()


def down(db):
    """SQLite doesn't support DROP COLUMN; additive migrations are never rolled back."""
    pass

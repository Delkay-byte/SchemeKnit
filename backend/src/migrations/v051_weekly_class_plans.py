"""Migration v051: authoritative weekly class-plan storage.

Creates the relational weekly-plan table used by the hosted application.
Identity, owner and revision are columns; the plan document is JSONB on
PostgreSQL (JSON on SQLite). Additive and non-destructive: the legacy JSON
file is not read, rewritten or deleted by this migration.
"""

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text

from ..database import engine

MIGRATION_VERSION = "v051_weekly_class_plans"
MIGRATION_NAME = "PostgreSQL-backed weekly class plans with revisions"


def up(db):
    inspector = sa_inspect(engine)
    if inspector.has_table("weekly_class_plans"):
        db.commit()
        return

    content_type = "JSONB" if engine.dialect.name == "postgresql" else "JSON"
    db.execute(text(
        """
        CREATE TABLE weekly_class_plans (
            id VARCHAR PRIMARY KEY,
            owner_id VARCHAR NOT NULL REFERENCES users(id),
            school_id VARCHAR REFERENCES schools(id),
            class_level VARCHAR NOT NULL DEFAULT '',
            week_number INTEGER NOT NULL DEFAULT 0,
            term VARCHAR NOT NULL DEFAULT '',
            academic_year VARCHAR NOT NULL DEFAULT '',
            template_id VARCHAR NOT NULL DEFAULT '',
            content %s NOT NULL,
            revision INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """ % content_type
    ))
    db.execute(text(
        "CREATE INDEX ix_weekly_class_plans_owner "
        "ON weekly_class_plans (owner_id)"
    ))
    db.execute(text(
        "CREATE INDEX ix_weekly_class_plans_owner_updated "
        "ON weekly_class_plans (owner_id, updated_at)"
    ))
    db.execute(text(
        "CREATE INDEX ix_weekly_class_plans_school "
        "ON weekly_class_plans (school_id)"
    ))
    db.commit()


def down(db):
    # Forward-only convention: dropping the authoritative plan table is
    # destructive and is intentionally not performed automatically.
    return

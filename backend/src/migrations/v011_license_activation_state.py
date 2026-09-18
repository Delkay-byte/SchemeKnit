"""
Migration v011: License activation state columns.

A school license created by Platform Admin starts `pending` and only becomes
usable when a school redeems an activation code. Until now nothing on the
license row recorded *that* moment, so the Platform Admin license view could
not distinguish "created" from "activated" and had no activation date to show.

Adds, additively and dialect-portably:
  activated_at      — when the first code was redeemed against this license
  activation_code_id — the ActivationCodeDB row that performed the redemption
"""

from sqlalchemy import text, inspect as sa_inspect
from ..database import engine

MIGRATION_VERSION = "v011_license_activation_state"
MIGRATION_NAME = "License activation state"


def up(db):
    """Add license activation-tracking columns when absent."""
    inspector = sa_inspect(engine)
    cols = []
    if inspector.has_table("school_licenses"):
        cols = [c["name"] for c in inspector.get_columns("school_licenses")]

    wanted = {
        "activated_at": "DATETIME",
        "activation_code_id": "VARCHAR",
    }
    for col, ddl in wanted.items():
        if col not in cols:
            db.execute(text(f"ALTER TABLE school_licenses ADD COLUMN {col} {ddl}"))
            db.commit()


def down(db):
    """SQLite doesn't support DROP COLUMN."""
    pass

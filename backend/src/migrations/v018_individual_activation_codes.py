"""
Migration v018: Individual teacher activation codes.

Adds the individual_activation_codes table for individual teacher license
activation codes (TF-IND-...) managed by the Platform Admin.
"""

from sqlalchemy import text, inspect as sa_inspect
from ..database import engine

MIGRATION_VERSION = "v018_individual_activation_codes"
MIGRATION_NAME = "Individual teacher activation codes"


def up(db):
    inspector = sa_inspect(engine)
    if inspector.has_table("individual_activation_codes"):
        return
    db.execute(text(
        """
        CREATE TABLE individual_activation_codes (
            id VARCHAR PRIMARY KEY,
            product_plan_id VARCHAR NOT NULL REFERENCES product_plans(id),
            code VARCHAR NOT NULL UNIQUE,
            status VARCHAR DEFAULT 'active',
            used_by_user_id VARCHAR REFERENCES users(id),
            used_at TIMESTAMP,
            created_at TIMESTAMP,
            expires_at TIMESTAMP
        )
        """
    ))
    db.execute(text(
        "CREATE INDEX ix_individual_activation_code ON individual_activation_codes (code)"
    ))
    db.commit()


def down(db):
    """SQLite-friendly teardown."""
    db.execute(text("DROP TABLE IF EXISTS individual_activation_codes"))
    db.commit()

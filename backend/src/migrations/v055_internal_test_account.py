"""Migration v055: owner-only internal test-account entitlement.

Adds ``users.is_internal_test_account`` (default false). The flag is the ONLY
source of unlimited application generation/AI for the owner's QA account and is
never accepted from a client request. Existing users are untouched and keep
their normal billing rules.

Forward-only: dropping the column would silently re-cap the account and lose
which historical usage was internal.
"""

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text

from ..database import engine

MIGRATION_VERSION = "v055_internal_test_account"
MIGRATION_NAME = "Owner-only internal test-account entitlement"


def up(db):
    inspector = sa_inspect(engine)
    if not inspector.has_table("users"):
        return
    columns = {col["name"] for col in inspector.get_columns("users")}
    if "is_internal_test_account" not in columns:
        db.execute(text(
            "ALTER TABLE users ADD COLUMN is_internal_test_account "
            "BOOLEAN NOT NULL DEFAULT FALSE"
        ))
    db.commit()


def down(db):
    # Forward-only by design: the entitlement is an explicit, auditable state.
    return

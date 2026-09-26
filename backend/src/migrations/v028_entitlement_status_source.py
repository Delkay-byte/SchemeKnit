"""
Migration v028: authoritative plan lifecycle on entitlements.

Adds the columns that make an account's plan explicit and admin-manageable:
  status          active | expired | revoked
  source          free | admin | payment | license | activation_code
  starts_at       when the current plan started
  activated_by / activated_at   which admin activated it, and when
  revoked_by / revoked_at / revoked_reason   revocation audit trail

Safe for existing data:
  * additive, nullable/defaulted columns only — no destructive change;
  * every existing account resolves to FREE unless its ``edition`` already
    grants a paid plan, so nobody is accidentally upgraded to PRO;
  * ``status`` is backfilled accurately from the existing ``expires_at``
    (elapsed -> "expired", otherwise "active").
"""

from datetime import datetime
from sqlalchemy import text, inspect as sa_inspect
from ..database import engine

MIGRATION_VERSION = "v028_entitlement_status_source"
MIGRATION_NAME = "Authoritative plan lifecycle on entitlements"


def _add_column(db, table, col, ddl, inspector):
    """Add a column only if the table exists and the column is missing."""
    if not inspector.has_table(table):
        return
    cols = [c["name"] for c in inspector.get_columns(table)]
    if col not in cols:
        db.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))
        db.commit()


def up(db):
    inspector = sa_inspect(engine)

    _add_column(db, "entitlements", "status", "VARCHAR DEFAULT 'active'", inspector)
    _add_column(db, "entitlements", "source", "VARCHAR DEFAULT 'free'", inspector)
    _add_column(db, "entitlements", "starts_at", "DATETIME", inspector)
    _add_column(db, "entitlements", "activated_by", "VARCHAR", inspector)
    _add_column(db, "entitlements", "activated_at", "DATETIME", inspector)
    _add_column(db, "entitlements", "revoked_by", "VARCHAR", inspector)
    _add_column(db, "entitlements", "revoked_at", "DATETIME", inspector)
    _add_column(db, "entitlements", "revoked_reason", "TEXT DEFAULT ''", inspector)

    if not inspector.has_table("entitlements"):
        return

    # Backfill status from the already-stored expiry. Anyone without a paid
    # edition remains FREE regardless of status; this only labels the row.
    db.execute(text(
        "UPDATE entitlements SET status = 'expired' "
        "WHERE expires_at IS NOT NULL AND expires_at < :now"
    ), {"now": datetime.utcnow()})
    db.execute(text(
        "UPDATE entitlements SET status = 'active' WHERE status IS NULL"
    ))
    db.execute(text(
        "UPDATE entitlements SET source = 'free' WHERE source IS NULL"
    ))
    db.commit()


def down(db):
    """SQLite cannot DROP COLUMN reliably; the added columns are harmless."""
    pass

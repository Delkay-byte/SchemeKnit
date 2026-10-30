"""Migration v039: distinguish recurring card vs prepaid Mobile Money.

Additive columns only. Card subscriptions keep `billing_mode=recurring`;
Mobile Money charges are `prepaid` (manual renewal) even though they use the
same subscription and licence rows.
"""

from sqlalchemy import text, inspect as sa_inspect
from ..database import engine

MIGRATION_VERSION = "v039_payment_method_modes"
MIGRATION_NAME = "Recurring card vs prepaid mobile money"


def _add(db, table, column, ddl):
    cols = [c["name"] for c in sa_inspect(engine).get_columns(table)]
    if column not in cols:
        db.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
        db.commit()


def up(db):
    if sa_inspect(engine).has_table("subscription_transactions"):
        _add(db, "subscription_transactions", "payment_method",
             "VARCHAR DEFAULT 'card_recurring'")
        _add(db, "subscription_transactions", "provider", "VARCHAR DEFAULT ''")
        _add(db, "subscription_transactions", "charge_status", "VARCHAR DEFAULT ''")
        _add(db, "subscription_transactions", "instructions", "TEXT DEFAULT ''")
    if sa_inspect(engine).has_table("user_subscriptions"):
        _add(db, "user_subscriptions", "billing_mode",
             "VARCHAR DEFAULT 'recurring'")
        _add(db, "user_subscriptions", "payment_method", "VARCHAR DEFAULT 'card'")
        _add(db, "user_subscriptions", "provider", "VARCHAR DEFAULT ''")


def down(db):
    # SQLite cannot drop columns; leave additive data in place.
    pass

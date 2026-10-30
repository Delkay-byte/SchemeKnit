"""Migration v037: bounded server-side logout revocation.

Access tokens are stateless JWTs. Logout now records the token's ``jti`` in a
small table so the same token is rejected before its natural expiry. Rows are
deleted once expired, so the table stays bounded by recent logouts.

Additive and dialect-portable: creates one table and two indexes only. Existing
tokens without a ``jti`` keep working (they simply cannot be individual targets
of logout), and no user data is rewritten.
"""

from sqlalchemy import text, inspect as sa_inspect
from ..database import engine

MIGRATION_VERSION = "v037_revoked_tokens"
MIGRATION_NAME = "Server-side logout token revocation"


def up(db):
    """Create ``revoked_tokens`` and its indexes (idempotent)."""
    if not sa_inspect(engine).has_table("revoked_tokens"):
        db.execute(text(
            "CREATE TABLE revoked_tokens ("
            "jti VARCHAR NOT NULL PRIMARY KEY, "
            "user_id VARCHAR NOT NULL, "
            "expires_at TIMESTAMP NOT NULL, "
            "revoked_at TIMESTAMP"
            ")"
        ))
        db.commit()
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_revoked_token_user "
        "ON revoked_tokens (user_id)"
    ))
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_revoked_token_expiry "
        "ON revoked_tokens (expires_at)"
    ))
    db.commit()


def down(db):
    """Drop the revocation table (safe: only session ids are stored)."""
    if sa_inspect(engine).has_table("revoked_tokens"):
        db.execute(text("DROP TABLE revoked_tokens"))
        db.commit()

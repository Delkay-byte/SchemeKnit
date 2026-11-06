"""Migration v053: session provenance and revocation replay store.

Phase 1.1 makes central logout revoke the *SSO-derived* sessions a product
created, without touching the same administrator's local (password) sessions.

That needs two additive changes:

``user_sessions`` gains
    * ``auth_source`` — ``local`` or ``sso``,
    * ``idp_sub``     — immutable Authentik subject of the SSO session,
    * ``idp_sid``     — OIDC session id, so an IdP back-channel logout token
                        carrying ``sid`` matches exactly.

``oidc_revocation_events`` records processed revocation message ids so a
replayed or duplicated delivery is rejected/accepted idempotently rather than
revoking twice.

Additive and non-destructive: no existing column is altered or dropped, so live
sessions (which simply have ``auth_source`` NULL) keep working untouched.
"""

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text

from ..database import engine

MIGRATION_VERSION = "v053_session_provenance_revocation"
MIGRATION_NAME = "Session provenance and revocation replay store"


def _columns(db, table: str) -> set[str]:
    inspector = sa_inspect(engine)
    return {c["name"] for c in inspector.get_columns(table)}


def up(db):
    cols = _columns(db, "user_sessions")
    if "auth_source" not in cols:
        db.execute(text("ALTER TABLE user_sessions ADD COLUMN auth_source VARCHAR"))
    if "idp_sub" not in cols:
        db.execute(text("ALTER TABLE user_sessions ADD COLUMN idp_sub VARCHAR"))
    if "idp_sid" not in cols:
        db.execute(text("ALTER TABLE user_sessions ADD COLUMN idp_sid VARCHAR"))

    inspector = sa_inspect(engine)
    if not inspector.has_table("oidc_revocation_events"):
        db.execute(text(
            """
            CREATE TABLE oidc_revocation_events (
                event_id VARCHAR PRIMARY KEY,
                source VARCHAR NOT NULL DEFAULT 'control_center',
                received_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        ))

    # Lookup path for revocation by subject/session.
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_user_sessions_idp_sub "
        "ON user_sessions (idp_sub)"
    ))
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_user_sessions_idp_sid "
        "ON user_sessions (idp_sid)"
    ))
    db.commit()


def down(db):
    # Forward-only: dropping provenance would silently widen revocation scope
    # back to "all sessions of the user", which is the behaviour we replaced.
    return

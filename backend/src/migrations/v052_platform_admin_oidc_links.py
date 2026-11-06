"""Migration v052: platform-admin OIDC identity links.

Creates the additive ``platform_admin_oidc_links`` table binding a local
``users`` row (role ``platform_admin``) to the central BloomCore Identity
provider subject (``idp_sub``) for the platform-admin SSO feature. The row is
written only after the Control Center linking flow succeeds (a verified
association, or a local-credential proof for a pending one).

Additive and non-destructive: no existing table or column is altered, so the
local (non-SSO) login paths are untouched.
"""

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text

from ..database import engine

MIGRATION_VERSION = "v052_platform_admin_oidc_links"
MIGRATION_NAME = "Platform admin OIDC identity links"


def up(db):
    inspector = sa_inspect(engine)
    if inspector.has_table("platform_admin_oidc_links"):
        db.commit()
        return

    db.execute(text(
        """
        CREATE TABLE platform_admin_oidc_links (
            id VARCHAR PRIMARY KEY,
            user_id VARCHAR NOT NULL REFERENCES users(id),
            issuer VARCHAR NOT NULL,
            idp_sub VARCHAR NOT NULL UNIQUE,
            linked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            linked_via VARCHAR NOT NULL DEFAULT 'local_credential_proof',
            created_by VARCHAR NOT NULL DEFAULT ''
        )
        """
    ))
    db.execute(text(
        "CREATE INDEX ix_oidc_links_user ON platform_admin_oidc_links (user_id)"
    ))
    db.execute(text(
        "CREATE INDEX ix_oidc_links_issuer_sub "
        "ON platform_admin_oidc_links (issuer, idp_sub)"
    ))
    db.commit()


def down(db):
    # Forward-only convention: dropping the identity-link table is destructive
    # (it would force every SSO admin through the linking flow again) and is
    # intentionally not performed automatically.
    return

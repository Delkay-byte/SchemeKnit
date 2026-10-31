"""Migration v048: single-use Turnstile token digests."""
from sqlalchemy import inspect as sa_inspect, text

MIGRATION_VERSION = "v048_turnstile_tokens"
MIGRATION_NAME = "Cloudflare Turnstile token replay protection"


def up(db):
    if sa_inspect(db.get_bind()).has_table("turnstile_tokens"):
        return
    db.execute(text(
        "CREATE TABLE turnstile_tokens ("
        "id VARCHAR PRIMARY KEY, "
        "token_hash VARCHAR NOT NULL UNIQUE, "
        "action VARCHAR NOT NULL DEFAULT '', "
        "hostname VARCHAR NOT NULL DEFAULT '', "
        "expires_at TIMESTAMP NOT NULL, "
        "created_at TIMESTAMP NOT NULL)"
    ))
    db.execute(text(
        "CREATE INDEX ix_turnstile_tokens_expiry "
        "ON turnstile_tokens (expires_at)"
    ))
    db.commit()


def down(db):
    if sa_inspect(db.get_bind()).has_table("turnstile_tokens"):
        db.execute(text("DROP TABLE turnstile_tokens"))
        db.commit()

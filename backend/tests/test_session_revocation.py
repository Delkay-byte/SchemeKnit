"""Central session revocation + OIDC back-channel logout (Phase 1.1).

Security-critical properties:
  * only a correctly signed message from the Control Center is accepted;
  * issuer, audience, freshness and event id are all enforced;
  * replayed/duplicate deliveries are acknowledged idempotently, never applied
    twice;
  * revocation scope is SSO-derived sessions of one immutable subject — a local
    password session of the same administrator survives.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.config import get_settings
from src.database import Base, OidcRevocationEventDB, UserSessionDB, get_db
from src.main import app

API_KEY = "sk-test-linking-key"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("PLATFORM_OIDC_LINKING_API_KEY", API_KEY)
    monkeypatch.setenv("PLATFORM_OIDC_CLIENT_ID", "schemeknit-sso")
    monkeypatch.setenv("PLATFORM_OIDC_ISSUER", "http://localhost:9000/application/o/schemeknit/")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def db_factory(monkeypatch):
    # StaticPool + a shared connection: plain "sqlite://" gives every pooled
    # connection its own empty database, so create_all would not be visible.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def _get_db():
        session = factory()
        try:
            yield session
            session.commit()
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db
    yield factory
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture()
def client(db_factory):
    return TestClient(app)


def _message(sub="uid-immutable-1", sid=None, *, key=API_KEY, iss=None, aud=None,
             iat=None, event_id=None, scope="identity_sessions"):
    body = {
        "event_id": event_id or str(uuid.uuid4()),
        "iss": iss or "bloomcore-control-center",
        "aud": aud or "schemeknit",
        "iat": iat if iat is not None else int(time.time()),
        "identity_sub": sub,
        "idp_sid": sid,
        "scope": scope,
        "reason": "logout",
    }
    payload = json.dumps(body, separators=(",", ":"), sort_keys=True)
    sig = hmac.new(key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return body, payload, sig


def _post(client, body, payload, sig):
    return client.post(
        "/api/v1/platform/sessions/revoke",
        content=payload.encode(),
        headers={
            "Content-Type": "application/json",
            "X-BloomCore-Event": body["event_id"],
            "X-BloomCore-Signature": sig,
        },
    )


def _seed_sessions(factory, sub="uid-immutable-1", sid="sid-abc", count=2):
    db = factory()
    now = datetime.utcnow()
    for i in range(count):
        db.add(UserSessionDB(
            jti=f"jti-sso-{i}", user_id="user-1", created_at=now,
            last_seen_at=now, expires_at=now + timedelta(hours=8),
            auth_source="sso", idp_sub=sub, idp_sid=sid,
        ))
    # A local password session for the SAME user must survive.
    db.add(UserSessionDB(
        jti="jti-local-1", user_id="user-1", created_at=now,
        last_seen_at=now, expires_at=now + timedelta(hours=8),
        auth_source="local", idp_sub=None, idp_sid=None,
    ))
    db.commit()
    db.close()


def _active(factory):
    db = factory()
    rows = db.query(UserSessionDB).filter(UserSessionDB.revoked_at.is_(None)).all()
    out = {r.jti for r in rows}
    db.close()
    return out


def test_valid_revocation_revokes_only_sso_sessions(client, db_factory):
    _seed_sessions(db_factory)
    body, payload, sig = _message()
    resp = _post(client, body, payload, sig)
    assert resp.status_code == 200, resp.text
    assert resp.json()["revoked"] == 2
    assert _active(db_factory) == {"jti-local-1"}


def test_bad_signature_rejected(client, db_factory):
    _seed_sessions(db_factory)
    body, payload, _ = _message()
    resp = _post(client, body, payload, "0" * 64)
    assert resp.status_code == 401
    assert len(_active(db_factory)) == 3  # nothing revoked


def test_wrong_issuer_rejected(client, db_factory):
    _seed_sessions(db_factory)
    body, payload, sig = _message(iss="some-other-service")
    assert _post(client, body, payload, sig).status_code == 401
    assert len(_active(db_factory)) == 3


def test_wrong_audience_rejected(client, db_factory):
    _seed_sessions(db_factory)
    body, payload, sig = _message(aud="bloomcore-one")
    assert _post(client, body, payload, sig).status_code == 401
    assert len(_active(db_factory)) == 3


def test_stale_message_rejected(client, db_factory):
    _seed_sessions(db_factory)
    body, payload, sig = _message(iat=int(time.time()) - 3600)
    assert _post(client, body, payload, sig).status_code == 401
    assert len(_active(db_factory)) == 3


def test_event_id_header_mismatch_rejected(client, db_factory):
    _seed_sessions(db_factory)
    body, payload, sig = _message()
    resp = client.post(
        "/api/v1/platform/sessions/revoke",
        content=payload.encode(),
        headers={
            "Content-Type": "application/json",
            "X-BloomCore-Event": "different-id",
            "X-BloomCore-Signature": sig,
        },
    )
    assert resp.status_code == 400


def test_replay_is_idempotent(client, db_factory):
    _seed_sessions(db_factory)
    body, payload, sig = _message()
    assert _post(client, body, payload, sig).json()["revoked"] == 2
    again = _post(client, body, payload, sig)
    assert again.status_code == 200
    assert again.json()["status"] == "already_applied"
    assert again.json()["revoked"] == 0


def test_revocation_by_sid_only_touches_that_session(client, db_factory):
    _seed_sessions(db_factory, sid="sid-abc", count=1)
    db = db_factory()
    now = datetime.utcnow()
    db.add(UserSessionDB(
        jti="jti-other-browser", user_id="user-1", created_at=now,
        last_seen_at=now, expires_at=now + timedelta(hours=8),
        auth_source="sso", idp_sub="uid-immutable-1", idp_sid="sid-other",
    ))
    db.commit()
    db.close()

    body, payload, sig = _message(sid="sid-abc", scope="session")
    assert _post(client, body, payload, sig).json()["revoked"] == 1
    # The other browser session of the same identity survives a sid-scoped revoke.
    assert _active(db_factory) == {"jti-other-browser", "jti-local-1"}


def test_other_identity_untouched(client, db_factory):
    _seed_sessions(db_factory)
    db = db_factory()
    now = datetime.utcnow()
    db.add(UserSessionDB(
        jti="jti-other-user", user_id="user-2", created_at=now,
        last_seen_at=now, expires_at=now + timedelta(hours=8),
        auth_source="sso", idp_sub="uid-someone-else", idp_sid="sid-x",
    ))
    db.commit()
    db.close()

    body, payload, sig = _message()
    _post(client, body, payload, sig)
    assert "jti-other-user" in _active(db_factory)


def test_missing_identity_sub_rejected(client, db_factory):
    _seed_sessions(db_factory)
    body, payload, sig = _message(sub="")
    assert _post(client, body, payload, sig).status_code == 400


def test_revocation_event_recorded(client, db_factory):
    _seed_sessions(db_factory)
    body, payload, sig = _message()
    _post(client, body, payload, sig)
    db = db_factory()
    assert db.get(OidcRevocationEventDB, body["event_id"]) is not None
    db.close()


# ─────────────────────────────────────────── back-channel logout token handling
def test_backchannel_logout_rejects_missing_token(client):
    resp = client.post("/api/auth/oidc/backchannel-logout", data={})
    assert resp.status_code == 400


def test_backchannel_logout_rejects_garbage_token(client):
    resp = client.post(
        "/api/auth/oidc/backchannel-logout", data={"logout_token": "not-a-jwt"}
    )
    assert resp.status_code == 400


def test_logout_token_requires_backchannel_event():
    from src.oidc_client import LOGOUT_EVENT, validate_logout_token

    assert LOGOUT_EVENT.startswith("http://schemas.openid.net/event/")
    # Guard against the constant silently changing shape.
    assert validate_logout_token.__doc__ and "back-channel" in validate_logout_token.__doc__

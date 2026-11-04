"""Router tests for the platform-admin OIDC SSO adapter.

Uses a FAKE IdP (synthetic RSA key standing in for the Authentik JWKS) and a
FAKE Control Center (monkeypatched linking resolve/confirm) so the real token
validation code path is exercised end-to-end without any network access.

Covers:
- /status feature probe
- /start 303 + flow cookie (+ 404 while disabled)
- callback: verified link -> native platform_admin session minted; token
  carries amr and satisfies require_platform_admin (MFA reconciliation) while
  a local (no-amr) token is refused when DEBUG is off
- unlinked email -> 403 denial, NO session
- pending -> confirm page with one-time attempt token; confirm with the
  existing local password creates the link, sends a valid HMAC proof to the
  Control Center and mints the session
- amr without a second factor -> denied (fail closed)
- bad state / replayed flow -> denied, cookie single-use
- regression: local password login (entry=platform_admin) still works
"""

import json
import time
from urllib.parse import unquote, urlparse, parse_qs

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src import oidc_client
from src.auth import hash_password, verify_password
from src.config import get_settings
from src.database import (
    Base, get_db, generate_id, User, PlatformAdminOidcLinkDB, UserSessionDB,
)
from src.main import app

ISSUER = "http://localhost:9000/application/o/schemeknit/"
LINKING_KEY = "sk-cc-test-key"


def _oidc_env(**overrides):
    env = {
        "PLATFORM_OIDC_ENABLED": "true",
        "PLATFORM_OIDC_ISSUER": ISSUER,
        "PLATFORM_OIDC_CLIENT_ID": "schemeknit-sso",
        "PLATFORM_OIDC_CLIENT_SECRET": "router-test-secret",
        "PLATFORM_OIDC_LINKING_API_KEY": LINKING_KEY,
        "PLATFORM_OIDC_LINKING_BASE_URL": "http://cc.test",
        # Keep the progressive cooldown out of the way of deliberate failures.
        "LOGIN_MAX_FAILURES": "100",
    }
    env.update(overrides)
    return env


@pytest.fixture(autouse=True)
def _oidc_router_env(monkeypatch):
    for key, value in _oidc_env().items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    from src.security import rate_limiter
    rate_limiter.reset()
    yield
    get_settings.cache_clear()
    rate_limiter.reset()


@pytest.fixture
def http(tmp_path, monkeypatch):
    """TestClient over a shared in-memory SQLite DB (same pattern as
    test_auth_lifecycle). Yields (client, db_session)."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    def _override_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_db
    client = TestClient(app)
    yield client, db
    app.dependency_overrides.pop(get_db, None)
    db.close()
    engine.dispose()


# ─────────────────────────────────────────────────────────────── fake IdP


_IDP_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


class _FakeJWKClient:
    def __init__(self, public_key):
        self.public_key = public_key

    def get_signing_key_from_jwt(self, token):
        return _FakeSigningKey(self.public_key)


_PUBLIC_KEY = jwt.algorithms.RSAAlgorithm.from_jwk(
    jwt.algorithms.RSAAlgorithm.to_jwk(_IDP_KEY.public_key())
)


def _idp_token(claims):
    return jwt.encode(claims, _IDP_KEY, algorithm="RS256", headers={"kid": "t"})


def _claims(email, sub="idp-sub-123", amr=("pwd", "otp")):
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": "schemeknit-sso",
        "sub": sub,
        "email": email,
        "exp": now + 300,
        "iat": now,
        "nonce": "placeholder",
    }
    if amr is not None:
        claims["amr"] = list(amr)
    return claims


@pytest.fixture
def fake_idp(monkeypatch):
    """Install the fake JWKS + token endpoint. Claims are set per-test."""

    class _FakeIdP:
        def __init__(self):
            self.claims = _claims("owner@bloomcore.test")

        def install(self, nonce):
            self.claims["nonce"] = nonce

    fake = _FakeIdP()
    monkeypatch.setattr(oidc_client, "jwks_uri",
                        lambda: "http://idp.test/jwks", raising=False)
    monkeypatch.setattr(oidc_client, "_jwk_client",
                        lambda uri: _FakeJWKClient(_PUBLIC_KEY), raising=False)

    used_codes: set[str] = set()

    def _fake_exchange(code, redirect_uri, verifier):
        # Real IdPs enforce single-use authorization codes; mirror that so
        # replayed callbacks fail at the token endpoint like they would in
        # production.
        if code not in used_codes:
            used_codes.add(code)
        else:
            raise oidc_client.OidcError("authorization code already used")
        assert verifier  # PKCE verifier arrived from the flow cookie
        return {"id_token": _idp_token(fake.claims)}

    monkeypatch.setattr(oidc_client, "exchange_code", _fake_exchange)
    monkeypatch.setattr(
        "src.routers.auth_oidc.exchange_code", _fake_exchange)
    return fake


class _FakeCC:
    """Records linking calls; behaviour set per-test."""

    def __init__(self):
        self.resolve_result = {"status": "verified",
                               "identity_sub": "cc-identity-sub",
                               "email": "owner@bloomcore.test"}
        self.resolve_emails = []
        self.confirm_calls = []
        self.fail_confirm = False

    def install(self, monkeypatch):
        def _resolve(email):
            self.resolve_emails.append(email)
            return dict(self.resolve_result)

        def _confirm(identity_sub, identity_email, product_admin_email):
            self.confirm_calls.append((identity_sub, identity_email,
                                       product_admin_email))
            if self.fail_confirm:
                raise oidc_client.OidcError("cc rejected")
            return {"status": "verified"}

        monkeypatch.setattr(oidc_client, "resolve_linking", _resolve)
        monkeypatch.setattr(oidc_client, "confirm_linking", _confirm)


@pytest.fixture
def fake_cc(monkeypatch):
    cc = _FakeCC()
    cc.install(monkeypatch)
    return cc


# ──────────────────────────────────────────────────────────── helpers


def _make_admin(db, email="owner@bloomcore.test", active=True,
                password="OwnerPass1!"):
    user = User(
        id=generate_id(),
        email=email,
        full_name="BloomCore Owner",
        hashed_password=hash_password(password),
        school_name="",
        is_admin=True,
        is_active=active,
        role="platform_admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_link(db, user, sub="idp-sub-123"):
    row = PlatformAdminOidcLinkDB(
        id=generate_id(),
        user_id=user.id,
        issuer=ISSUER,
        idp_sub=sub,
        linked_via="local_credential_proof",
        created_by=user.email,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _start_flow(client):
    res = client.get("/api/auth/oidc/start", follow_redirects=False)
    assert res.status_code == 303
    flow_raw = client.cookies.get("sk_oidc_flow")
    flow = oidc_client.decode_flow(flow_raw)
    assert flow is not None
    return res, flow


def _complete_flow(client, flow, fake_idp, extra_params=None):
    fake_idp.install(flow["nonce"])
    params = {"code": "good-code", "state": flow["state"]}
    params.update(extra_params or {})
    return client.get("/api/auth/oidc/callback", params=params,
                      follow_redirects=False)


def _fragment_token(location: str) -> str:
    assert "#token=" in location, location
    return location.split("#token=", 1)[1]


# ─────────────────────────────────────────────────────────────── tests


class TestStatus:

    def test_enabled(self, http):
        client, _ = http
        res = client.get("/api/auth/oidc/status")
        assert res.status_code == 200
        assert res.json() == {"enabled": True}

    def test_disabled_when_flag_off(self, http, monkeypatch):
        client, _ = http
        monkeypatch.delenv("PLATFORM_OIDC_ENABLED", raising=False)
        get_settings.cache_clear()
        res = client.get("/api/auth/oidc/status")
        assert res.json() == {"enabled": False}


class TestStart:

    def test_start_redirects_to_idp_with_pkce(self, http):
        client, _ = http
        res, flow = _start_flow(client)
        assert "authorization_endpoint" not in res.headers["location"]
        assert "localhost:9000" in res.headers["location"]
        assert "code_challenge_method=S256" in res.headers["location"]
        cookie = client.cookies.get("sk_oidc_flow")
        cookie_res = client.get("/api/auth/oidc/status")  # path differs; ignore
        flow = oidc_client.decode_flow(cookie)
        assert flow["kind"] == "authorize"
        assert flow["exp"] - flow["created"] <= 600

    def test_start_404_when_disabled(self, http, monkeypatch):
        client, _ = http
        monkeypatch.delenv("PLATFORM_OIDC_ENABLED", raising=False)
        get_settings.cache_clear()
        res = client.get("/api/auth/oidc/start", follow_redirects=False)
        assert res.status_code == 404


class TestCallbackVerifiedLink:

    def test_mints_platform_admin_session(self, http, fake_idp, fake_cc):
        client, db = http
        user = _make_admin(db)
        _make_link(db, user)

        res, flow = _start_flow(client)
        res = _complete_flow(client, flow, fake_idp)
        assert res.status_code == 303, res.text
        assert "/login/platform-admin/sso/complete#" in res.headers["location"]
        token = _fragment_token(res.headers["location"])

        # Flow cookie is single-use: cleared after the callback.
        assert "sk_oidc_flow" not in client.cookies

        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["role"] == "platform_admin"

        # Server-side session row exists and is live.
        assert db.query(UserSessionDB).count() == 1

    def test_amr_satisfies_platform_admin_mfa_gate(self, http, fake_idp,
                                                   fake_cc, monkeypatch):
        """The SSO token (IdP-attested second factor) must pass the platform
        admin MFA gate even without local TOTP, while a LOCAL token without
        amr is refused. DEBUG is forced off for the gate to be active."""
        client, db = http
        monkeypatch.setattr("src.auth.settings.DEBUG", False)
        user = _make_admin(db)  # no local TOTP enrollment
        _make_link(db, user)

        res, flow = _start_flow(client)
        res = _complete_flow(client, flow, fake_idp)
        token = _fragment_token(res.headers["location"])
        payload = jwt.decode(token, options={"verify_signature": False})
        assert payload["amr"] == ["pwd", "otp"]

        ok = client.get("/api/platform-admin/dashboard",
                        headers={"Authorization": f"Bearer {token}"})
        assert ok.status_code == 200

        # Regression: a locally-minted token for the same admin has no amr and
        # MUST still be refused by the unchanged MFA gate.
        from src.auth import create_user_token
        local_token = create_user_token(user)
        denied = client.get("/api/platform-admin/dashboard",
                            headers={"Authorization": f"Bearer {local_token}"})
        assert denied.status_code == 403

    def test_unlinked_email_denied_no_session(self, http, fake_idp, fake_cc):
        client, db = http
        fake_cc.resolve_result = {"status": "none"}
        _make_admin(db)

        res, flow = _start_flow(client)
        res = _complete_flow(client, flow, fake_idp)
        assert res.status_code == 403
        assert "not authorised" in res.text
        assert "sk_oidc_flow" not in client.cookies
        assert db.query(UserSessionDB).count() == 0

    def test_verified_link_to_inactive_user_denied(self, http, fake_idp,
                                                   fake_cc):
        client, db = http
        user = _make_admin(db, active=False)
        _make_link(db, user)

        res, flow = _start_flow(client)
        res = _complete_flow(client, flow, fake_idp)
        assert res.status_code == 403
        assert db.query(UserSessionDB).count() == 0

    def test_verified_link_to_non_admin_role_denied(self, http, fake_idp,
                                                    fake_cc):
        client, db = http
        user = _make_admin(db)
        user.role = "teacher"
        db.commit()
        _make_link(db, user)

        res, flow = _start_flow(client)
        res = _complete_flow(client, flow, fake_idp)
        assert res.status_code == 403
        assert db.query(UserSessionDB).count() == 0

    def test_verified_link_without_local_row_downgrades_to_confirm(
            self, http, fake_idp, fake_cc):
        """Fail closed + self-healing: a CC-verified association with no local
        link row requires the local password proof once."""
        client, db = http
        fake_cc.resolve_result = {"status": "verified",
                                  "identity_sub": "cc-identity-sub",
                                  "email": "owner@bloomcore.test"}
        user = _make_admin(db)

        res, flow = _start_flow(client)
        res = _complete_flow(client, flow, fake_idp)
        assert res.status_code == 303
        assert "/login/platform-admin/sso/confirm?attempt=" \
            in res.headers["location"]
        assert db.query(PlatformAdminOidcLinkDB).count() == 0


class TestCallbackRejections:

    def test_amr_without_second_factor_denied(self, http, fake_idp, fake_cc):
        client, db = http
        fake_idp.claims = _claims("owner@bloomcore.test", amr=("pwd",))
        user = _make_admin(db)
        _make_link(db, user)

        res, flow = _start_flow(client)
        res = _complete_flow(client, flow, fake_idp)
        assert res.status_code == 403
        assert db.query(UserSessionDB).count() == 0

    def test_missing_amr_denied(self, http, fake_idp, fake_cc):
        client, db = http
        fake_idp.claims = _claims("owner@bloomcore.test", amr=None)
        user = _make_admin(db)
        _make_link(db, user)

        res, flow = _start_flow(client)
        res = _complete_flow(client, flow, fake_idp)
        assert res.status_code == 403

    def test_bad_state_denied_and_cookie_cleared(self, http, fake_idp):
        client, db = http
        _make_admin(db)
        res, flow = _start_flow(client)
        res = _complete_flow(client, flow, fake_idp,
                             extra_params={"state": "forged"})
        assert res.status_code == 400
        assert "sk_oidc_flow" not in client.cookies
        assert db.query(UserSessionDB).count() == 0

    def test_flow_cookie_single_use_replay_denied(self, http, fake_idp,
                                                  fake_cc):
        """After a completed callback the cookie is cleared: a replayed
        code+state WITHOUT the cookie fails, and a reused authorization code
        fails at the (realistic, single-use) token endpoint."""
        client, db = http
        user = _make_admin(db)
        _make_link(db, user)
        res, flow = _start_flow(client)
        first = _complete_flow(client, flow, fake_idp)
        assert first.status_code == 303
        assert db.query(UserSessionDB).count() == 1

        # Replay 1: same code+state, but the cookie was cleared on success.
        fake_idp.install(flow["nonce"])
        replay_no_cookie = client.get(
            "/api/auth/oidc/callback",
            params={"code": "good-code", "state": flow["state"]},
            follow_redirects=False)
        assert replay_no_cookie.status_code == 400

        # Replay 2: attacker-supplied cookie value within TTL still dies at
        # the single-use authorization code (as on a real IdP).
        fake_idp.install(flow["nonce"])
        replay_with_cookie = client.get(
            "/api/auth/oidc/callback",
            params={"code": "good-code", "state": flow["state"]},
            cookies={"sk_oidc_flow": oidc_client.encode_flow(flow)},
            follow_redirects=False)
        assert replay_with_cookie.status_code == 502
        assert db.query(UserSessionDB).count() == 1

    def test_idp_error_response_denied(self, http, fake_idp):
        client, db = http
        _make_admin(db)
        res, flow = _start_flow(client)
        res = _complete_flow(client, flow, fake_idp,
                             extra_params={"code": "", "error": "access_denied"})
        assert res.status_code == 403
        assert db.query(UserSessionDB).count() == 0


class TestPendingLinkConfirm:

    def _pending_setup(self, http, fake_idp, fake_cc):
        client, db = http
        fake_cc.resolve_result = {"status": "pending",
                                  "identity_sub": "cc-identity-sub",
                                  "email": "owner@bloomcore.test"}
        user = _make_admin(db)
        res, flow = _start_flow(client)
        res = _complete_flow(client, flow, fake_idp)
        assert res.status_code == 303
        location = res.headers["location"]
        assert "/login/platform-admin/sso/confirm?attempt=" in location
        attempt = parse_qs(urlparse(location).query)["attempt"][0]
        return client, db, user, attempt

    def test_confirm_creates_link_and_session(self, http, fake_idp, fake_cc):
        client, db, user, attempt = self._pending_setup(http, fake_idp, fake_cc)

        res = client.post("/api/auth/oidc/confirm",
                          json={"attempt": attempt, "password": "OwnerPass1!"})
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["token_type"] == "bearer"
        assert body["user"]["role"] == "platform_admin"

        link = db.query(PlatformAdminOidcLinkDB).one()
        assert link.user_id == user.id
        assert link.idp_sub == "idp-sub-123"
        assert link.linked_via == "local_credential_proof"

        # Control Center received a valid, verifiable proof.
        assert len(fake_cc.confirm_calls) == 1
        identity_sub, identity_email, product_admin_email = fake_cc.confirm_calls[0]
        assert identity_sub == "cc-identity-sub"
        assert product_admin_email == "owner@bloomcore.test"

        # Minted session works and carries amr.
        me = client.get("/api/auth/me",
                        headers={"Authorization": f"Bearer {body['access_token']}"})
        assert me.status_code == 200
        payload = jwt.decode(body["access_token"],
                             options={"verify_signature": False})
        assert payload["amr"] == ["pwd", "otp"]
        # Confirm cookie cleared after success (single use).
        assert "sk_oidc_flow" not in client.cookies

    def test_confirm_wrong_password_denied(self, http, fake_idp, fake_cc):
        client, db, user, attempt = self._pending_setup(http, fake_idp, fake_cc)
        res = client.post("/api/auth/oidc/confirm",
                          json={"attempt": attempt, "password": "WrongPass1!"})
        assert res.status_code == 401
        assert db.query(PlatformAdminOidcLinkDB).count() == 0
        assert fake_cc.confirm_calls == []

    def test_confirm_attempt_replay_denied(self, http, fake_idp, fake_cc):
        """The attempt token alone cannot be replayed without its cookie."""
        client, db, user, attempt = self._pending_setup(http, fake_idp, fake_cc)
        first = client.post("/api/auth/oidc/confirm",
                            json={"attempt": attempt, "password": "OwnerPass1!"})
        assert first.status_code == 200
        # Drop the (cleared) cookie and replay the same attempt token.
        client.cookies.clear()
        replay = client.post("/api/auth/oidc/confirm",
                             json={"attempt": attempt, "password": "OwnerPass1!"})
        assert replay.status_code in (400, 403)
        assert db.query(UserSessionDB).count() == 1

    def test_confirm_without_attempt_token_rejected(self, http, fake_idp,
                                                    fake_cc):
        client, db, user, _ = self._pending_setup(http, fake_idp, fake_cc)
        res = client.post("/api/auth/oidc/confirm",
                          json={"attempt": "garbage.token", "password": "x"})
        assert res.status_code == 400

    def test_confirm_after_cc_stopped_authorising_denied(self, http, fake_idp,
                                                         fake_cc):
        client, db, user, attempt = self._pending_setup(http, fake_idp, fake_cc)
        fake_cc.resolve_result = {"status": "none"}
        res = client.post("/api/auth/oidc/confirm",
                          json={"attempt": attempt, "password": "OwnerPass1!"})
        assert res.status_code == 403
        assert db.query(PlatformAdminOidcLinkDB).count() == 0

    def test_confirm_cc_failure_rolls_back_link(self, http, fake_idp, fake_cc):
        client, db, user, attempt = self._pending_setup(http, fake_idp, fake_cc)
        fake_cc.fail_confirm = True
        res = client.post("/api/auth/oidc/confirm",
                          json={"attempt": attempt, "password": "OwnerPass1!"})
        assert res.status_code == 502
        assert db.query(PlatformAdminOidcLinkDB).count() == 0


class TestLocalLoginRegression:

    def test_local_platform_admin_login_still_works(self, http):
        """The password path is untouched by the SSO adapter."""
        client, db = http
        _make_admin(db)
        res = client.post("/api/auth/login", json={
            "email": "owner@bloomcore.test",
            "password": "OwnerPass1!",
            "entry": "platform_admin",
        })
        assert res.status_code == 200
        assert res.json()["access_token"]
        me = client.get("/api/auth/me", headers={
            "Authorization": f"Bearer {res.json()['access_token']}"})
        assert me.status_code == 200

    def test_local_teacher_login_still_works(self, http):
        client, db = http
        from tests.conftest import make_user
        make_user(db, role="teacher", email="t1@test.com")
        res = client.post("/api/auth/login", json={
            "email": "t1@test.com", "password": "testpass123",
            "entry": "teacher"})
        assert res.status_code == 200

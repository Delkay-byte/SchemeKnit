"""Unit tests for the OIDC client validation core (platform-admin SSO).

Uses synthetic RSA keys (no network, no real IdP): tokens are signed locally
and the JWKS lookup is replaced with a fake key set. Covers:

- valid token (signature, issuer, audience, nonce, exp/iat)
- bad signature (second RSA key — simulates a token from a different IdP)
- wrong issuer / wrong audience / expired / nonce mismatch
- amr second-factor reconciliation (fail closed)
- flow cookie round-trip + expiry
- HMAC attempt token round-trip + tamper rejection
"""

import base64
import hashlib
import hmac
import json
import time
from urllib.parse import unquote

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from src import oidc_client
from src.config import get_settings


OIDC_ENV = {
    "PLATFORM_OIDC_ENABLED": "true",
    "PLATFORM_OIDC_ISSUER": "https://idp.test/application/o/schemeknit/",
    "PLATFORM_OIDC_CLIENT_ID": "schemeknit-sso",
    "PLATFORM_OIDC_CLIENT_SECRET": "unit-test-secret",
    "PLATFORM_OIDC_LINKING_API_KEY": "unit-test-secret",
}


def _rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def _oidc_settings(monkeypatch):
    for key, value in OIDC_ENV.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


class _FakeJWKClient:
    """Stand-in for PyJWKClient bound to ONE synthetic public key."""

    def __init__(self, public_key):
        self.public_key = public_key

    def get_signing_key_from_jwt(self, token):
        return _FakeSigningKey(self.public_key)


def _public_from_key(private_key):
    return jwt.algorithms.RSAAlgorithm.from_jwk(
        jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key())
    )


def _install_jwks(monkeypatch, private_key):
    monkeypatch.setattr(
        oidc_client, "jwks_uri", lambda: "https://idp.test/jwks", raising=False)
    client = _FakeJWKClient(_public_from_key(private_key))
    monkeypatch.setattr(oidc_client, "_jwk_client", lambda uri: client,
                        raising=False)


def _make_token(private_key, claims, headers=None):
    return jwt.encode(claims, private_key, algorithm="RS256",
                      headers=headers or {"kid": "test-key"})


def _base_claims(**overrides):
    now = int(time.time())
    claims = {
        "iss": "https://idp.test/application/o/schemeknit/",
        "aud": "schemeknit-sso",
        "sub": "idp-sub-123",
        "email": "owner@bloomcore.com",
        "exp": now + 300,
        "iat": now,
        "nonce": "nonce-abc",
        "amr": ["pwd", "otp"],
    }
    claims.update(overrides)
    return claims


class TestIdTokenValidation:

    def test_valid_token_passes(self, monkeypatch):
        key = _rsa_key()
        _install_jwks(monkeypatch, key)
        claims = oidc_client.validate_id_token(
            _make_token(key, _base_claims()), "nonce-abc")
        assert claims["sub"] == "idp-sub-123"
        assert claims["email"] == "owner@bloomcore.com"

    def test_bad_signature_rejected(self, monkeypatch):
        """A token signed by a DIFFERENT key (e.g. another IdP) must fail."""
        real_key = _rsa_key()
        rogue_key = _rsa_key()
        _install_jwks(monkeypatch, real_key)
        with pytest.raises(oidc_client.OidcError):
            oidc_client.validate_id_token(
                _make_token(rogue_key, _base_claims()), "nonce-abc")

    def test_wrong_issuer_rejected(self, monkeypatch):
        key = _rsa_key()
        _install_jwks(monkeypatch, key)
        with pytest.raises(oidc_client.OidcError):
            oidc_client.validate_id_token(_make_token(key, _base_claims(
                iss="https://evil.test/application/o/schemeknit/")), "nonce-abc")

    def test_wrong_audience_rejected(self, monkeypatch):
        key = _rsa_key()
        _install_jwks(monkeypatch, key)
        with pytest.raises(oidc_client.OidcError):
            oidc_client.validate_id_token(_make_token(key, _base_claims(
                aud="another-product")), "nonce-abc")

    def test_expired_token_rejected(self, monkeypatch):
        key = _rsa_key()
        _install_jwks(monkeypatch, key)
        now = int(time.time())
        with pytest.raises(oidc_client.OidcError):
            oidc_client.validate_id_token(_make_token(key, _base_claims(
                exp=now - 120, iat=now - 600)), "nonce-abc")

    def test_nonce_mismatch_rejected(self, monkeypatch):
        """Single-use nonce: a replayed token bound to another flow must fail."""
        key = _rsa_key()
        _install_jwks(monkeypatch, key)
        with pytest.raises(oidc_client.OidcError, match="nonce"):
            oidc_client.validate_id_token(
                _make_token(key, _base_claims()), "a-different-nonce")

    def test_missing_nonce_rejected(self, monkeypatch):
        key = _rsa_key()
        _install_jwks(monkeypatch, key)
        with pytest.raises(oidc_client.OidcError, match="nonce"):
            oidc_client.validate_id_token(
                _make_token(key, _base_claims()), "")

    def test_missing_email_rejected(self, monkeypatch):
        key = _rsa_key()
        _install_jwks(monkeypatch, key)
        claims = _base_claims()
        del claims["email"]
        with pytest.raises(oidc_client.OidcError):
            oidc_client.validate_id_token(
                _make_token(key, claims), "nonce-abc")

    def test_leeway_allows_small_skew(self, monkeypatch):
        """exp 20s in the past is tolerated (30s leeway), 60s is not."""
        key = _rsa_key()
        _install_jwks(monkeypatch, key)
        now = int(time.time())
        claims = oidc_client.validate_id_token(_make_token(key, _base_claims(
            exp=now - 20, iat=now - 200)), "nonce-abc")
        assert claims["sub"]
        with pytest.raises(oidc_client.OidcError):
            oidc_client.validate_id_token(_make_token(key, _base_claims(
                exp=now - 60, iat=now - 300)), "nonce-abc")


class TestAmrReconciliation:

    def test_password_plus_otp_is_second_factor(self):
        assert oidc_client.amr_has_second_factor(["pwd", "otp"]) is True

    def test_password_plus_webauthn_is_second_factor(self):
        assert oidc_client.amr_has_second_factor(["pwd", "webauthn"]) is True

    def test_bare_mfa_marker_is_second_factor(self):
        assert oidc_client.amr_has_second_factor(["mfa"]) is True

    def test_password_only_fails_closed(self):
        assert oidc_client.amr_has_second_factor(["pwd"]) is False

    def test_absent_amr_fails_closed(self):
        assert oidc_client.amr_has_second_factor([]) is False

    def test_amr_from_claims_handles_string(self):
        assert oidc_client.amr_from_claims({"amr": "pwd"}) == ["pwd"]


class TestPkcePair:

    def test_verifier_matches_challenge(self):
        verifier, challenge = oidc_client.create_pkce_pair()
        derived = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).decode().rstrip("=")
        assert challenge == derived

    def test_pairs_are_unique(self):
        assert oidc_client.create_pkce_pair()[0] != oidc_client.create_pkce_pair()[0]


class TestFlowCookie:

    def test_round_trip(self):
        flow = {"kind": "authorize", "state": "s", "nonce": "n",
                "verifier": "v", "exp": time.time() + 60}
        raw = oidc_client.encode_flow(flow)
        assert unquote(raw) == json.dumps(flow, separators=(",", ":"))
        decoded = oidc_client.decode_flow(raw)
        assert decoded["state"] == "s"

    def test_expired_flow_rejected(self):
        flow = {"kind": "authorize", "state": "s", "exp": time.time() - 30}
        assert oidc_client.decode_flow(oidc_client.encode_flow(flow)) is None

    def test_garbage_rejected(self):
        assert oidc_client.decode_flow("not-a-flow") is None
        assert oidc_client.decode_flow(None) is None

    def test_flow_ttl_is_capped(self):
        assert oidc_client._flow_ttl() <= oidc_client.MAX_FLOW_TTL_SECONDS


class TestAttemptToken:

    def test_round_trip(self):
        token = oidc_client.sign_attempt_token({"kind": "oidc-link-confirm",
                                                "email": "a@b.c"})
        data = oidc_client.verify_attempt_token(token)
        assert data["email"] == "a@b.c"

    def test_expired_attempt_rejected(self):
        token = oidc_client.sign_attempt_token({"kind": "x"}, ttl_seconds=-10)
        assert oidc_client.verify_attempt_token(token) is None

    def test_tampered_payload_rejected(self):
        token = oidc_client.sign_attempt_token({"kind": "x", "email": "a@b.c"})
        raw, _, sig = token.rpartition(".")
        forged = base64.urlsafe_b64encode(
            json.dumps({"kind": "x", "email": "evil@b.c"}).encode()
        ).decode().rstrip("=")
        assert oidc_client.verify_attempt_token(f"{forged}.{sig}") is None

    def test_tampered_signature_rejected(self):
        token = oidc_client.sign_attempt_token({"kind": "x"})
        raw, _, _ = token.rpartition(".")
        bad_sig = "0" * 64
        assert oidc_client.verify_attempt_token(f"{raw}.{bad_sig}") is None


class TestLinkingProof:

    def _verify_like_control_center(self, payload: str, signature: str,
                                    key: str):
        """Mirror of the Control Center's verify_linking_proof primitive
        (docs/security/ACCOUNT-LINKING.md): hex HMAC-SHA256 over the exact
        payload string, keyed by the per-product API key, plus a staleness
        window. Kept local so the suite never imports across repos."""
        data = json.loads(payload)
        expected = hmac.new(key.encode(), payload.encode(),
                            hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            return None
        if abs(time.time() - int(data.get("ts", 0))) > 300:
            return None
        return data

    def test_proof_verifies_with_product_key(self):
        proof = oidc_client.build_linking_proof(
            "sub-1", "id@x.y", "admin@schemeknit.test")
        data = self._verify_like_control_center(
            proof["payload"], proof["signature"], "unit-test-secret")
        assert data is not None
        assert data["product"] == "schemeknit"
        assert data["identity_sub"] == "sub-1"
        assert data["product_admin_email"] == "admin@schemeknit.test"

    def test_proof_is_canonical_sorted_json(self):
        proof = oidc_client.build_linking_proof(
            "sub-1", "id@x.y", "admin@schemeknit.test")
        keys = list(json.loads(proof["payload"]).keys())
        assert keys == sorted(keys)

    def test_proof_rejected_with_wrong_key(self):
        proof = oidc_client.build_linking_proof("sub-1", "id@x.y", "a@b.c")
        assert self._verify_like_control_center(
            proof["payload"], proof["signature"], "not-the-key") is None

    def test_proof_rejects_tampered_payload(self):
        proof = oidc_client.build_linking_proof("sub-1", "id@x.y", "a@b.c")
        tampered = json.loads(proof["payload"])
        tampered["identity_sub"] = "attacker-sub"
        assert self._verify_like_control_center(
            json.dumps(tampered, sort_keys=True), proof["signature"],
            "unit-test-secret") is None

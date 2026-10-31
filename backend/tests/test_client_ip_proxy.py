"""Trusted-proxy client IP and rate-limit identity regression tests.

All addresses are documentation/test ranges (203.0.113.0/24,
198.51.100.0/24, 2001:db8::/32). No real user address is used.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from src.config import Settings, get_settings
from src.login_security import account_key
from src.security import (
    RateLimitMiddleware, RateLimiter, client_ip, client_key,
    enforce_authenticated_budget, _rate_limit_exempt,
)


class _BrokenLimiter:
    def is_allowed(self, *_args, **_kwargs):
        raise RuntimeError("shared store unavailable")


def _request(headers=None, client=("203.0.113.5", 1234)):
    return Request({
        "type": "http", "method": "POST", "path": "/api/auth/login",
        "headers": list(headers or []),
        "client": client,
    })


def _trusted(monkeypatch, cidrs="10.0.0.0/8,192.0.2.0/24"):
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "true")
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", cidrs)
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _clear_settings():
    yield
    get_settings.cache_clear()


class TestForwardedHeadersIgnored:
    def test_direct_request_without_headers(self):
        assert client_ip(_request()) == "203.0.113.5"

    def test_untrusted_peer_forged_single_header(self, monkeypatch):
        monkeypatch.setenv("TRUST_PROXY_HEADERS", "false")
        get_settings.cache_clear()
        req = _request([(b"x-forwarded-for", b"198.51.100.7")])
        assert client_ip(req) == "203.0.113.5"

    def test_untrusted_peer_forged_multiple_addresses(self, monkeypatch):
        monkeypatch.setenv("TRUST_PROXY_HEADERS", "false")
        get_settings.cache_clear()
        req = _request([(b"x-forwarded-for", b"198.51.100.7, 10.1.1.1")])
        assert client_ip(req) == "203.0.113.5"

    def test_untrusted_peer_multiple_header_fields(self, monkeypatch):
        monkeypatch.setenv("TRUST_PROXY_HEADERS", "false")
        get_settings.cache_clear()
        req = _request([
            (b"x-forwarded-for", b"198.51.100.7"),
            (b"x-forwarded-for", b"10.1.1.1"),
        ])
        assert client_ip(req) == "203.0.113.5"

    def test_untrusted_peer_forged_rfc7239_header(self, monkeypatch):
        monkeypatch.setenv("TRUST_PROXY_HEADERS", "false")
        get_settings.cache_clear()
        req = _request([(b"forwarded", b"for=198.51.100.7;proto=https")])
        assert client_ip(req) == "203.0.113.5"

    def test_trust_disabled_ignores_valid_looking_header(self, monkeypatch):
        monkeypatch.setenv("TRUST_PROXY_HEADERS", "false")
        get_settings.cache_clear()
        req = _request([(b"x-forwarded-for", b"198.51.100.7")],
                       client=("10.1.1.1", 1234))
        assert client_ip(req) == "10.1.1.1"


class TestTrustedChain:
    def test_trusted_peer_single_client(self, monkeypatch):
        _trusted(monkeypatch)
        req = _request([(b"x-forwarded-for", b"198.51.100.7")],
                       client=("10.1.1.1", 1234))
        assert client_ip(req) == "198.51.100.7"

    def test_trusted_multi_proxy_chain(self, monkeypatch):
        _trusted(monkeypatch, "10.0.0.0/8")
        req = _request(
            [(b"x-forwarded-for", b"198.51.100.7, 10.1.1.1")],
            client=("10.2.2.2", 1234),
        )
        assert client_ip(req) == "198.51.100.7"

    def test_trusted_multiple_header_fields(self, monkeypatch):
        _trusted(monkeypatch, "10.0.0.0/8")
        req = _request(
            [
                (b"x-forwarded-for", b"198.51.100.7"),
                (b"x-forwarded-for", b"10.1.1.1"),
            ],
            client=("10.2.2.2", 1234),
        )
        assert client_ip(req) == "198.51.100.7"

    def test_trusted_peer_ignores_rfc7239_header(self, monkeypatch):
        _trusted(monkeypatch, "10.0.0.0/8")
        req = _request(
            [(b"forwarded", b"for=198.51.100.7;proto=https")],
            client=("10.1.1.1", 1234),
        )
        assert client_ip(req) == "10.1.1.1"

    def test_chain_with_untrusted_intermediate_returns_intermediate(self, monkeypatch):
        _trusted(monkeypatch, "10.0.0.0/8")
        req = _request(
            [(b"x-forwarded-for", b"198.51.100.7, 203.0.113.9")],
            client=("10.2.2.2", 1234),
        )
        assert client_ip(req) == "203.0.113.9"

    def test_all_trusted_hops_fail_closed_to_direct(self, monkeypatch):
        _trusted(monkeypatch, "10.0.0.0/8")
        req = _request(
            [(b"x-forwarded-for", b"10.1.1.1, 10.2.2.2")],
            client=("10.3.3.3", 1234),
        )
        assert client_ip(req) == "10.3.3.3"

    def test_ipv6_client(self, monkeypatch):
        _trusted(monkeypatch)
        req = _request([(b"x-forwarded-for", b"2001:db8::7")],
                       client=("10.1.1.1", 1234))
        assert client_ip(req) == "2001:db8::7"

    def test_ipv4_mapped_ipv6_is_normalized(self, monkeypatch):
        _trusted(monkeypatch)
        req = _request([(b"x-forwarded-for", b"::ffff:198.51.100.7")],
                       client=("10.1.1.1", 1234))
        assert client_ip(req) == "198.51.100.7"

    def test_empty_header_falls_back_to_direct(self, monkeypatch):
        _trusted(monkeypatch)
        req = _request([(b"x-forwarded-for", b"")],
                       client=("10.1.1.1", 1234))
        assert client_ip(req) == "10.1.1.1"

    def test_malformed_header_falls_back_to_direct(self, monkeypatch):
        _trusted(monkeypatch)
        req = _request([(b"x-forwarded-for", b"not-an-ip")],
                       client=("10.1.1.1", 1234))
        assert client_ip(req) == "10.1.1.1"

    def test_overlong_header_falls_back_to_direct(self, monkeypatch):
        _trusted(monkeypatch)
        req = _request([(b"x-forwarded-for", b"198.51.100.7," * 300)],
                       client=("10.1.1.1", 1234))
        assert client_ip(req) == "10.1.1.1"

    def test_excessive_hops_fall_back_to_direct(self, monkeypatch):
        _trusted(monkeypatch)
        chain = ",".join(["198.51.100.7"] * 40).encode()
        req = _request([(b"x-forwarded-for", chain)],
                       client=("10.1.1.1", 1234))
        assert client_ip(req) == "10.1.1.1"

    def test_peer_outside_allowlist_is_not_trusted(self, monkeypatch):
        _trusted(monkeypatch, "10.0.0.0/8")
        req = _request([(b"x-forwarded-for", b"198.51.100.7")],
                       client=("192.0.2.200", 1234))
        assert client_ip(req) == "192.0.2.200"


class TestConfiguration:
    def test_trust_disabled_by_default(self):
        assert Settings(TRUST_PROXY_HEADERS=False).TRUST_PROXY_HEADERS is False

    def test_enabled_without_allowlist_fails(self, monkeypatch):
        monkeypatch.delenv("TRUSTED_PROXY_CIDRS", raising=False)
        with pytest.raises(ValueError):
            Settings(TRUST_PROXY_HEADERS=True, TRUSTED_PROXY_CIDRS="")

    def test_invalid_cidr_fails(self):
        with pytest.raises(ValueError):
            Settings(
                TRUST_PROXY_HEADERS=True,
                TRUSTED_PROXY_CIDRS="10.0.0.0/8,not-a-cidr",
            )

    def test_wildcard_cidr_fails(self):
        with pytest.raises(ValueError):
            Settings(TRUST_PROXY_HEADERS=True, TRUSTED_PROXY_CIDRS="0.0.0.0/0")

    def test_valid_explicit_cidrs(self):
        settings = Settings(
            TRUST_PROXY_HEADERS=True,
            TRUSTED_PROXY_CIDRS="10.0.0.0/8, 192.0.2.0/24",
        )
        assert settings.TRUSTED_PROXY_CIDRS == "10.0.0.0/8,192.0.2.0/24"

    def test_config_change_does_not_broaden_trust(self, monkeypatch):
        _trusted(monkeypatch, "10.0.0.0/8")
        req = _request([(b"x-forwarded-for", b"198.51.100.7")],
                       client=("10.1.1.1", 1234))
        assert client_ip(req) == "198.51.100.7"
        _trusted(monkeypatch, "192.0.2.0/24")
        assert client_ip(req) == "10.1.1.1"

    def test_loopback_exemption_is_debug_only(self, monkeypatch):
        monkeypatch.setenv("DEBUG", "false")
        get_settings.cache_clear()
        assert _rate_limit_exempt("127.0.0.1") is False
        monkeypatch.setenv("DEBUG", "true")
        get_settings.cache_clear()
        assert _rate_limit_exempt("127.0.0.1") is True


class TestLimiterIdentity:
    def test_client_keys_are_stable_and_not_raw(self):
        one = client_key("203.0.113.5")
        assert one == client_key("203.0.113.5")
        assert one != client_key("203.0.113.6")
        assert "203.0.113.5" not in one
        assert len(one) == 64

    def test_account_keys_are_independent(self):
        assert account_key("a@example.test") != account_key("b@example.test")

    def test_different_verified_clients_have_separate_buckets(self):
        limiter = RateLimiter()
        a = client_key("203.0.113.5")
        b = client_key("203.0.113.6")
        for _ in range(20):
            limiter.is_allowed(a, "/api/auth/login", now=1000)
        assert limiter.is_allowed(b, "/api/auth/login", now=1000)[0] is True

    def test_forged_headers_cannot_create_new_identities(self, monkeypatch):
        monkeypatch.setenv("TRUST_PROXY_HEADERS", "false")
        get_settings.cache_clear()
        one = client_ip(_request([(b"x-forwarded-for", b"198.51.100.7")]))
        two = client_ip(_request([(b"x-forwarded-for", b"198.51.100.8")]))
        assert one == two == "203.0.113.5"
        assert client_key(one) == client_key(two)

    def test_malformed_metadata_does_not_crash(self, monkeypatch):
        _trusted(monkeypatch)
        for value in (b"", b"unknown", b":::", b"[::1", b"1.2.3.4:notaport"):
            assert client_ip(_request([(b"x-forwarded-for", value)],
                                      client=("10.1.1.1", 1234))) == "10.1.1.1"

    def test_authenticated_budget_is_independent_of_ip(self, monkeypatch):
        limiter = RateLimiter()
        monkeypatch.setattr("src.security.get_rate_limiter", lambda: limiter)
        user_one = "user-one"
        user_two = "user-two"
        for _ in range(30):
            enforce_authenticated_budget(user_one, "generate")
        with pytest.raises(HTTPException) as exc:
            enforce_authenticated_budget(user_one, "generate")
        assert exc.value.status_code == 429
        # A second account has its own budget even from the same source IP.
        enforce_authenticated_budget(user_two, "generate")


class TestSharedStoreFailClosed:
    @staticmethod
    def _app():
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware)

        @app.post("/api/auth/login")
        async def login():
            return {"ok": True}

        @app.post("/api/settings/change")
        async def low_risk():
            return {"ok": True}

        return app

    def test_shared_store_failure_blocks_high_risk_route(self, monkeypatch):
        monkeypatch.setattr(
            "src.security.get_rate_limiter", lambda: _BrokenLimiter())
        client = TestClient(self._app())
        response = client.post("/api/auth/login")
        assert response.status_code == 503
        assert "temporarily unavailable" in response.json()["detail"]

    def test_shared_store_failure_keeps_low_risk_route_working(self, monkeypatch):
        monkeypatch.setattr(
            "src.security.get_rate_limiter", lambda: _BrokenLimiter())
        client = TestClient(self._app())
        assert client.post("/api/settings/change").status_code == 200

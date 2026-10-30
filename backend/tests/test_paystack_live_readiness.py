"""Live-mode configuration and Paystack transport safety tests."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import paystack  # noqa: E402


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in (
        "PAYSTACK_SECRET_KEY", "PAYSTACK_PUBLIC_KEY",
        "NEXT_PUBLIC_PAYSTACK_PUBLIC_KEY", "PAYSTACK_MODE",
        "PAYSTACK_ENABLED", "PAYSTACK_CURRENCY",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("PAYSTACK_CURRENCY", "GHS")
    yield monkeypatch


def test_missing_secret_fails_safely():
    with pytest.raises(paystack.PaystackError) as exc:
        paystack.environment()
    assert exc.value.status_code == 503
    assert "No payment was taken" in exc.value.message


def test_malformed_secret_fails_safely(clean_env):
    clean_env.setenv("PAYSTACK_SECRET_KEY", "not-a-paystack-key")
    with pytest.raises(paystack.PaystackError):
        paystack.environment()


def test_live_key_is_refused_unless_mode_is_live(clean_env):
    clean_env.setenv("PAYSTACK_SECRET_KEY", "sk_live_placeholder")
    with pytest.raises(paystack.PaystackError) as exc:
        paystack.environment()
    assert "PAYSTACK_MODE" in exc.value.message


def test_live_key_with_live_mode_is_accepted(clean_env):
    clean_env.setenv("PAYSTACK_SECRET_KEY", "sk_live_placeholder")
    clean_env.setenv("PAYSTACK_MODE", "live")
    assert paystack.environment() == "live"


def test_test_key_with_live_mode_is_refused(clean_env):
    clean_env.setenv("PAYSTACK_SECRET_KEY", "sk_test_placeholder")
    clean_env.setenv("PAYSTACK_MODE", "live")
    with pytest.raises(paystack.PaystackError):
        paystack.environment()


def test_secret_key_in_public_variable_is_refused(clean_env):
    clean_env.setenv("PAYSTACK_SECRET_KEY", "sk_test_placeholder")
    clean_env.setenv("NEXT_PUBLIC_PAYSTACK_PUBLIC_KEY", "sk_test_placeholder")
    with pytest.raises(paystack.PaystackError) as exc:
        paystack.environment()
    assert "secret key" in exc.value.message.lower()


def test_payments_can_be_disabled_explicitly(clean_env):
    clean_env.setenv("PAYSTACK_SECRET_KEY", "sk_test_placeholder")
    clean_env.setenv("PAYSTACK_ENABLED", "false")
    with pytest.raises(paystack.PaystackError) as exc:
        paystack.environment()
    assert exc.value.status_code == 503
    assert "disabled" in exc.value.message.lower()


def test_invalid_currency_is_refused(clean_env):
    clean_env.setenv("PAYSTACK_SECRET_KEY", "sk_test_placeholder")
    clean_env.setenv("PAYSTACK_CURRENCY", "NGN")
    with pytest.raises(paystack.PaystackError):
        paystack.environment()


class _Resp:
    ok = True
    status_code = 200

    def json(self):
        return {"status": True, "data": {"status": "success"}}


def test_api_uses_https_tls_verification_and_no_redirects(clean_env, monkeypatch):
    clean_env.setenv("PAYSTACK_SECRET_KEY", "sk_test_placeholder")
    seen = {}

    def fake_request(method, url, **kwargs):
        seen.update({"method": method, "url": url, **kwargs})
        return _Resp()

    monkeypatch.setattr("requests.request", fake_request)
    paystack._api("GET", "/transaction/verify/ref")
    assert seen["url"].startswith("https://api.paystack.co/")
    assert seen["verify"] is True
    assert seen["allow_redirects"] is False
    assert seen["headers"]["Authorization"].startswith("Bearer sk_test_")
    assert "sk_test_" not in str(seen.get("json") or "")


def test_signature_requires_configured_secret(clean_env):
    assert paystack.verify_signature(b"{}", "abc") is False


def test_production_boot_rejects_test_key():
    from src.config import Settings

    settings = Settings(
        DEBUG=False, PAYSTACK_ENABLED=True, PAYSTACK_MODE="test",
        PAYSTACK_SECRET_KEY="sk_test_placeholder",
        PAYSTACK_CURRENCY="GHS", SECRET_KEY="x", JWT_SECRET_KEY="y",
    )
    with pytest.raises(RuntimeError) as exc:
        settings.validate_production()
    message = str(exc.value)
    assert "PAYSTACK_MODE" in message
    assert "PAYSTACK_SECRET_KEY" in message


def test_production_boot_accepts_explicit_live_configuration():
    from src.config import Settings

    settings = Settings(
        DEBUG=False, PAYSTACK_ENABLED=True, PAYSTACK_MODE="live",
        PAYSTACK_SECRET_KEY="sk_live_placeholder",
        PAYSTACK_CURRENCY="GHS", SECRET_KEY="x", JWT_SECRET_KEY="y",
    )
    with pytest.raises(RuntimeError) as exc:
        settings.validate_production()
    message = str(exc.value)
    assert "PAYSTACK_MODE" not in message
    assert "PAYSTACK_SECRET_KEY" not in message
    assert "PAYSTACK_CURRENCY" not in message

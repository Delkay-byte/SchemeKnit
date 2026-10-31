"""Security alert adapter: structured logging plus optional webhook delivery."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from src.logging_config import alert_security  # noqa: E402


def test_no_webhook_configuration_reports_not_delivered(monkeypatch):
    from src.config import get_settings
    monkeypatch.setenv("SECURITY_ALERT_WEBHOOK_URL", "")
    get_settings.cache_clear()
    try:
        assert alert_security("security_test", account="hashed") is False
    finally:
        get_settings.cache_clear()


def test_configured_webhook_delivers_and_returns_true(monkeypatch):
    from src.config import get_settings
    seen = {}

    class Resp:
        status_code = 200

    def post(url, json=None, timeout=None):
        seen.update({"url": url, "json": json, "timeout": timeout})
        return Resp()

    monkeypatch.setenv("SECURITY_ALERT_WEBHOOK_URL", "https://alerts.example.test/hook")
    get_settings.cache_clear()
    monkeypatch.setattr("requests.post", post)
    try:
        assert alert_security(
            "account_cooldown", severity="warning",
            account="hmac-value", cooldown_seconds=60) is True
        assert seen["url"].startswith("https://alerts.example.test")
        assert seen["json"]["event"] == "account_cooldown"
        assert "password" not in seen["json"]
        assert "token" not in seen["json"]
    finally:
        get_settings.cache_clear()


def test_webhook_failure_never_raises(monkeypatch):
    from src.config import get_settings
    monkeypatch.setenv("SECURITY_ALERT_WEBHOOK_URL", "https://alerts.example.test/hook")
    get_settings.cache_clear()

    def post(*args, **kwargs):
        raise RuntimeError("down")

    monkeypatch.setattr("requests.post", post)
    try:
        assert alert_security("mfa_failed", account="hmac") is False
    finally:
        get_settings.cache_clear()

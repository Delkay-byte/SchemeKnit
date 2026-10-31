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
    import src.logging_config as logging_config
    logging_config._alert_last_sent.clear()
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


def test_owner_email_fallback_is_used_when_webhook_is_empty(monkeypatch):
    from src.config import get_settings
    import src.email_service as email_service

    class FakeEmail:
        def __init__(self):
            self.sent = []

        def send_owner_alert(self, to, subject, summary):
            self.sent.append((to, subject, summary))
            return type("R", (), {"success": True})()

    fake = FakeEmail()
    monkeypatch.setenv("SECURITY_ALERT_WEBHOOK_URL", "")
    monkeypatch.setenv("OWNER_ALERT_EMAIL", "owner@example.test")
    get_settings.cache_clear()
    monkeypatch.setattr(email_service, "get_email", lambda: fake)
    try:
        assert alert_security("owner_email_test", severity="info",
                              service="api") is True
        assert fake.sent and fake.sent[0][0] == "owner@example.test"
        assert "owner_email_test" in fake.sent[0][2]
        assert "password" not in fake.sent[0][2].lower()
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

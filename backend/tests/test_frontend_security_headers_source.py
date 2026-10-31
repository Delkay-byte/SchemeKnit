"""Static contract for the deployed Next.js security headers."""
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[2] / "frontend" / "next.config.js"


def test_frontend_headers_are_enforced_without_unsafe_eval():
    text = CONFIG.read_text(encoding="utf-8")
    for fragment in (
        "Content-Security-Policy",
        "Strict-Transport-Security",
        "X-Content-Type-Options",
        "Referrer-Policy",
        "Permissions-Policy",
        "frame-ancestors 'self'",
        "object-src 'none'",
    ):
        assert fragment in text
    assert "unsafe-eval" not in text
    assert "https://checkout.paystack.com" in text


def test_private_pages_are_no_store():
    text = CONFIG.read_text(encoding="utf-8")
    assert "Cache-Control" in text
    assert "no-store" in text
    assert "(dashboard|upload|review|generate|lessons|settings" in text

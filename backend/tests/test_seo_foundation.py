"""Static SEO foundation checks for the Next.js public site."""
from __future__ import annotations

from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
APP = FRONTEND / "src" / "app"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def test_homepage_title_has_no_mojibake_and_uses_brand():
    layout = _text(APP / "layout.tsx")
    assert "SchemeKnit" in layout
    assert "\uFFFD" not in layout
    assert "Lesson Plan Generator" in layout


def test_centralized_site_url_and_metadata_helpers_exist():
    helper = _text(FRONTEND / "src" / "lib" / "site-url.ts")
    assert "NEXT_PUBLIC_SITE_URL" in helper
    assert "alternates" in helper and "canonical" in helper
    assert "openGraph" in helper and "twitter" in helper


def test_sitemap_and_robots_exist_and_exclude_private_paths():
    sitemap = _text(APP / "sitemap.ts")
    robots = _text(APP / "robots.ts")
    for public in ("/", "/features", "/pricing", "/help", "/privacy-policy"):
        assert f"'{public}'" in sitemap
    for private in ("/dashboard", "/login", "/payments", "/platform-admin"):
        assert f"'{private}'" in robots
    assert "sitemap.xml" in robots


def test_private_routes_get_noindex_header_and_staging_noindex():
    middleware = _text(FRONTEND / "src" / "middleware.ts")
    assert "X-Robots-Tag" in middleware
    assert "noindex, nofollow" in middleware
    assert "IS_STAGING" in middleware


def test_structured_data_is_present_and_factual():
    component = _text(FRONTEND / "src" / "components" / "site-structured-data.tsx")
    assert "Organization" in component
    assert "WebSite" in component
    assert "SoftwareApplication" in component
    assert "aggregateRating" not in component
    assert "review" not in component.lower()


def test_public_pages_have_page_metadata():
    expected = {
        "about/page.tsx": "/about",
        "features/page.tsx": "/features",
        "how-it-works/page.tsx": "/how-it-works",
        "help/page.tsx": "/help",
        "pricing/layout.tsx": "/pricing",
        "contact/page.tsx": "/contact",
        "privacy-policy/page.tsx": "/privacy-policy",
        "terms/page.tsx": "/terms",
        "data-retention/page.tsx": "/data-retention",
        "refunds-cancellation/page.tsx": "/refunds-cancellation",
        "license-subscription/page.tsx": "/license-subscription",
    }
    for relative, path in expected.items():
        text = _text(APP / relative)
        assert "pageMetadata" in text, relative
        assert f"path: '{path}'" in text, relative

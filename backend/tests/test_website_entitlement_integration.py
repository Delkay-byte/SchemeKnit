"""Website copy and entitlement integration pinning the approved catalogue."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import catalogue  # noqa: E402

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"
PRICING = FRONTEND / "app" / "pricing" / "page.tsx"
UPGRADE = FRONTEND / "app" / "(app)" / "upgrade" / "page.tsx"


def test_pricing_page_fallback_matches_backend_catalogue():
    source = PRICING.read_text(encoding="utf-8")
    for package in catalogue.PACKAGES:
        assert package.slug in source, package.slug
        assert str(package.price_pesewas) in source, package.slug
        assert str(package.credits) in source, package.slug


def test_pricing_page_exposes_only_approved_packages():
    source = PRICING.read_text(encoding="utf-8")
    assert "teacher-annual" not in source
    assert "school-monthly" not in source
    assert "automatic renewal" in source


def test_upgrade_offers_only_bank_transfer_and_mobile_money():
    source = UPGRADE.read_text(encoding="utf-8")
    assert "bank_transfer" in source
    assert "mobile_money" in source
    assert "initializePaystack" not in source
    assert "channels" not in source
    assert "card checkout" not in source.lower()
    assert "card payment" not in source.lower()


def test_landing_page_states_the_approved_differentiator_and_free_allowance():
    source = (FRONTEND / "app" / "page.tsx").read_text(encoding="utf-8")
    assert "Two free lesson plans every month" in source
    assert "Start Free" in source
    assert "View Pricing" in source
    hero = (FRONTEND / "components" / "landing" / "landing-hero.tsx").read_text(encoding="utf-8")
    assert "Your Scheme of Learning." in hero
    assert "Your Lesson Plans." in hero
    assert "Made Easier." in hero
    steps = (FRONTEND / "components" / "landing" / "how-it-works.tsx").read_text(encoding="utf-8")
    assert "Upload a DOCX or PDF scheme" in steps or "Upload your scheme" in steps
    assert "three separate" in steps
    assert "Basic 1–6" in steps


def test_no_old_prices_in_public_pages():
    old = ("GH₵59", "GH₵149", "GH₵480", "GH₵500", "Teacher Annual", "School Monthly")
    for path in (
        FRONTEND / "app" / "pricing" / "page.tsx",
        FRONTEND / "app" / "page.tsx",
        FRONTEND / "app" / "features" / "page.tsx",
        FRONTEND / "app" / "license-subscription" / "page.tsx",
    ):
        source = path.read_text(encoding="utf-8")
        for token in old:
            assert token not in source, f"{token} still present in {path.name}"

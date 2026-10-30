"""Authoritative TeachFlow package catalogue.

This module is the single source of truth for every sellable package: its
price, credit allowance, validity and payment terms. The database is seeded
from it (migrations v041/v042) and the API reads the database, so the landing
page, pricing page, upgrade page, checkout, entitlement service and dashboard
all resolve the same values.

Never accept a price, credit count or validity from the client.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

CURRENCY = "GHS"

PACKAGE_KIND_FREE = "free"
PACKAGE_KIND_FLEXIBLE = "flexible"
PACKAGE_KIND_TIMED = "timed"


@dataclass(frozen=True)
class Package:
    slug: str
    name: str
    price_pesewas: int
    credits: int
    validity_days: Optional[int]
    kind: str
    description: str
    features: Tuple[str, ...] = field(default_factory=tuple)
    purchasable: bool = True
    display_order: int = 0
    payment_terms: str = "One-time prepaid payment. No automatic renewal."

    @property
    def price_ghs(self) -> float:
        return self.price_pesewas / 100

    @property
    def validity_label(self) -> str:
        if self.kind == PACKAGE_KIND_FREE:
            return "Resets monthly"
        if self.validity_days is None:
            return "Credits do not expire"
        return f"{self.validity_days} days"

    def entitlements(self) -> dict:
        """Feature flags written onto the entitlement row on activation."""
        return {
            # Credits, not a monthly generation cap, bound a paid package.
            "generation_limit": 0,
            "batch_generation": True,
            "zip_export": True,
            "pdf_export": True,
            "ai_enabled": True,
            "ai_credits": 0,
            "credit_allowance": self.credits,
            "credit_validity_days": self.validity_days,
            "package_kind": self.kind,
        }


FREE = Package(
    slug="free",
    name="Free",
    price_pesewas=0,
    credits=2,
    validity_days=None,
    kind=PACKAGE_KIND_FREE,
    description="Two lesson-plan generations every calendar month.",
    features=(
        "2 indicator-level lesson plans per month",
        "Upload DOCX or PDF schemes of learning",
        "Review and correct extracted curriculum",
        "Edit, save and export generated plans",
    ),
    purchasable=False,
    display_order=0,
    payment_terms="Free. No payment information required.",
)

FLEXIBLE_CREDIT_PACK = Package(
    slug="flexible-credit-pack",
    name="Flexible Credit Pack",
    price_pesewas=1200,
    credits=20,
    validity_days=None,
    kind=PACKAGE_KIND_FLEXIBLE,
    description="Twenty lesson-plan credits that stay available until used.",
    features=(
        "20 indicator-level lesson plans",
        "Credits never expire",
        "Use them whenever you need them",
        "No automatic renewal",
    ),
    display_order=1,
)

TEACHER_MONTHLY = Package(
    slug="teacher-monthly",
    name="Teacher Monthly",
    price_pesewas=2200,
    credits=40,
    validity_days=30,
    kind=PACKAGE_KIND_TIMED,
    description="Forty lesson-plan credits for thirty days.",
    features=(
        "40 indicator-level lesson plans",
        "Available for 30 days",
        "Full batch generation within your credits",
        "No automatic renewal",
    ),
    display_order=2,
)

TEACHER_TERM_PASS = Package(
    slug="teacher-term-pass",
    name="Teacher Term Pass",
    price_pesewas=5000,
    credits=160,
    validity_days=120,
    kind=PACKAGE_KIND_TIMED,
    description="One hundred and sixty lesson-plan credits for a school term.",
    features=(
        "160 indicator-level lesson plans",
        "Available for 120 days",
        "Full batch generation within your credits",
        "No automatic renewal",
    ),
    display_order=3,
)

ACADEMIC_YEAR_PASS = Package(
    slug="academic-year-pass",
    name="Academic Year Pass",
    price_pesewas=12000,
    credits=480,
    validity_days=365,
    kind=PACKAGE_KIND_TIMED,
    description="Four hundred and eighty lesson-plan credits for a full academic year.",
    features=(
        "480 indicator-level lesson plans",
        "Available for 365 days",
        "Full batch generation within your credits",
        "No automatic renewal",
    ),
    display_order=4,
)

PACKAGES: Tuple[Package, ...] = (
    FREE,
    FLEXIBLE_CREDIT_PACK,
    TEACHER_MONTHLY,
    TEACHER_TERM_PASS,
    ACADEMIC_YEAR_PASS,
)

BY_SLUG = {p.slug: p for p in PACKAGES}

#: Slugs that existed before the approved catalogue. They stay in the database
#: for historical transactions and existing customers but cannot be bought.
LEGACY_SLUGS: Tuple[str, ...] = ("teacher-annual", "school-monthly")


def get(slug: str) -> Optional[Package]:
    return BY_SLUG.get(slug)


def purchasable() -> Tuple[Package, ...]:
    return tuple(p for p in PACKAGES if p.purchasable)


def free_package() -> Package:
    return FREE


def seeds() -> Tuple[dict, ...]:
    """Rows used by the migration and by tests that seed a catalogue."""
    rows = []
    for p in PACKAGES:
        rows.append({
            "slug": p.slug,
            "name": p.name,
            "description": p.description,
            "price_pesewas": p.price_pesewas,
            "currency": CURRENCY,
            "interval": "one_time" if p.purchasable else "free",
            "duration_days": p.validity_days or 0,
            "features": list(p.features),
            "entitlements": p.entitlements(),
            "active": bool(p.purchasable),
            "package_kind": p.kind,
            "credit_allowance": p.credits,
            "credit_validity_days": p.validity_days,
            "display_order": p.display_order,
            "payment_terms": p.payment_terms,
        })
    return tuple(rows)

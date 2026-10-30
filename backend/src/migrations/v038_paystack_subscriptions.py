"""Migration v038: Paystack subscriptions, payments and automatic licensing.

Additive only. Creates the subscription catalogue, per-user subscription,
transaction ledger, webhook idempotency ledger, status history and per-user
licence tables. Seeds the three catalogue plans from the prices already present
in ``product_plans`` (Teacher Monthly GHS 50, Teacher Annual GHS 480, School
Monthly GHS 500). No existing table or row is modified.
"""

from sqlalchemy import text, inspect as sa_inspect

from ..database import (
    Base, engine, SubscriptionPlanDB,
)

MIGRATION_VERSION = "v038_paystack_subscriptions"
MIGRATION_NAME = "Paystack subscriptions, payments and automatic licensing"

_TABLES = (
    "subscription_plans",
    "user_subscriptions",
    "subscription_transactions",
    "paystack_webhook_events",
    "subscription_events",
    "user_licenses",
)

# Approved prices already recorded in product_plans (GHS -> pesewas).
_SEED = (
    dict(
        slug="teacher-monthly", name="Teacher Monthly",
        description="Unlimited lesson planning for one teacher, billed monthly.",
        price_pesewas=5000, interval="monthly", duration_days=30,
        features=["Unlimited lesson plans", "All export formats",
                  "AI lesson assistance", "Curriculum workspace"],
        entitlements=dict(generation_limit=0, batch_generation=True,
                          zip_export=True, pdf_export=True, ai_enabled=True,
                          ai_credits=0),
    ),
    dict(
        slug="teacher-annual", name="Teacher Annual",
        description="Unlimited lesson planning for one teacher, billed annually.",
        price_pesewas=48000, interval="annual", duration_days=365,
        features=["Everything in Teacher Monthly", "Two months free",
                  "Priority support"],
        entitlements=dict(generation_limit=0, batch_generation=True,
                          zip_export=True, pdf_export=True, ai_enabled=True,
                          ai_credits=0),
    ),
    dict(
        slug="school-monthly", name="School Monthly",
        description="Unlimited planning for a school team, billed monthly.",
        price_pesewas=50000, interval="monthly", duration_days=30,
        features=["Up to 10 teachers", "All export formats",
                  "AI lesson assistance", "School administration"],
        entitlements=dict(generation_limit=0, batch_generation=True,
                          zip_export=True, pdf_export=True, ai_enabled=True,
                          ai_credits=0, seat_limit=10),
    ),
)


def up(db):
    inspector = sa_inspect(engine)
    for name in _TABLES:
        if inspector.has_table(name):
            continue
        table = Base.metadata.tables.get(name)
        if table is not None:
            table.create(bind=engine, checkfirst=True)
    db.commit()

    from ..database import generate_id
    for plan in _SEED:
        exists = db.execute(
            text("SELECT 1 FROM subscription_plans WHERE slug = :slug"),
            {"slug": plan["slug"]},
        ).first()
        if exists:
            continue
        db.execute(
            text(
                "INSERT INTO subscription_plans "
                "(id, slug, name, description, price_pesewas, currency, interval, "
                "duration_days, features, entitlements, active, "
                "paystack_test_plan_code, paystack_live_plan_code) "
                "VALUES (:id, :slug, :name, :desc, :price, 'GHS', :interval, "
                ":days, CAST(:features AS JSON), CAST(:entitlements AS JSON), "
                "TRUE, '', '')"
            ),
            {
                "id": generate_id(), "slug": plan["slug"], "name": plan["name"],
                "desc": plan["description"], "price": plan["price_pesewas"],
                "interval": plan["interval"], "days": plan["duration_days"],
                "features": __import__("json").dumps(plan["features"]),
                "entitlements": __import__("json").dumps(plan["entitlements"]),
            },
        )
    db.commit()


def down(db):
    inspector = sa_inspect(engine)
    for name in reversed(_TABLES):
        if inspector.has_table(name):
            db.execute(text(f"DROP TABLE {name}"))
    db.commit()

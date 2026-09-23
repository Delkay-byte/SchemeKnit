"""
Migration v013: Individual Teacher Subscription Architecture.

Extends the existing entitlement/licensing tables to support individual teacher
subscriptions alongside the existing school licensing model. No new tables are
created — existing tables are extended with additive, nullable columns.

Changes:
  - users: subscription_type (individual | school | null)
  - product_plans: customer_type, generation_limit, batch_generation, zip_export,
    pdf_export, custom_template_limit, history_limit, ai_enabled, ai_credits,
    max_generations_per_period
  - entitlements: subscription_type, generation_limit, generations_used,
    batch_generation, zip_export, pdf_export, custom_template_limit,
    history_limit, ai_credits, ai_credits_used
  - Seeds FREE_TEACHER and TEACHER_PRO product plans
"""

from datetime import datetime
from sqlalchemy import text, inspect as sa_inspect
from ..database import engine

MIGRATION_VERSION = "v013_individual_teacher_plan"
MIGRATION_NAME = "Individual Teacher Subscription Architecture"


def _add_column(db, table, col, ddl, inspector):
    """Add a column only if the table exists and the column doesn't."""
    if inspector.has_table(table):
        cols = [c["name"] for c in inspector.get_columns(table)]
        if col not in cols:
            db.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))
            db.commit()


def _seed_plan(db, plan_data, inspector):
    """Insert a product plan only if one with that name doesn't exist."""
    if not inspector.has_table("product_plans"):
        return
    try:
        existing = db.execute(
            text("SELECT id FROM product_plans WHERE name = :name"),
            {"name": plan_data["name"]},
        ).fetchone()
    except Exception:
        return
    if not existing:
        db.execute(
            text(
                "INSERT INTO product_plans "
                "(id, name, description, product_type, price, currency, duration_days, "
                " seat_limit, features, educational_levels, template_access, ai_access, "
                " content_access, active, created_at, updated_at, "
                " customer_type, generation_limit, batch_generation, zip_export, "
                " pdf_export, custom_template_limit, history_limit, "
                " ai_enabled, ai_credits, max_generations_per_period) "
                "VALUES "
                "(:id, :name, :description, :product_type, :price, :currency, "
                ":duration_days, :seat_limit, :features, :educational_levels, "
                ":template_access, :ai_access, :content_access, :active, "
                ":created_at, :updated_at, "
                ":customer_type, :generation_limit, :batch_generation, :zip_export, "
                ":pdf_export, :custom_template_limit, :history_limit, "
                ":ai_enabled, :ai_credits, :max_generations_per_period)"
            ),
            plan_data,
        )
        db.commit()


def up(db):
    inspector = sa_inspect(engine)
    now = datetime.utcnow().isoformat()

    # ── users table ────────────────────────────────────────────────────────
    _add_column(db, "users", "subscription_type",
                "TEXT DEFAULT NULL", inspector)

    # ── product_plans table ────────────────────────────────────────────────
    _add_column(db, "product_plans", "customer_type",
                "TEXT DEFAULT 'school'", inspector)
    _add_column(db, "product_plans", "generation_limit",
                "INTEGER DEFAULT 0", inspector)
    _add_column(db, "product_plans", "batch_generation",
                "BOOLEAN DEFAULT FALSE", inspector)
    _add_column(db, "product_plans", "zip_export",
                "BOOLEAN DEFAULT FALSE", inspector)
    _add_column(db, "product_plans", "pdf_export",
                "BOOLEAN DEFAULT FALSE", inspector)
    _add_column(db, "product_plans", "custom_template_limit",
                "INTEGER DEFAULT 0", inspector)
    _add_column(db, "product_plans", "history_limit",
                "INTEGER DEFAULT 0", inspector)
    _add_column(db, "product_plans", "ai_enabled",
                "BOOLEAN DEFAULT FALSE", inspector)
    _add_column(db, "product_plans", "ai_credits",
                "INTEGER DEFAULT 0", inspector)
    _add_column(db, "product_plans", "max_generations_per_period",
                "INTEGER DEFAULT 0", inspector)

    # ── entitlements table ─────────────────────────────────────────────────
    _add_column(db, "entitlements", "subscription_type",
                "TEXT DEFAULT NULL", inspector)
    _add_column(db, "entitlements", "generation_limit",
                "INTEGER DEFAULT 0", inspector)
    _add_column(db, "entitlements", "generations_used",
                "INTEGER DEFAULT 0", inspector)
    _add_column(db, "entitlements", "batch_generation",
                "BOOLEAN DEFAULT FALSE", inspector)
    _add_column(db, "entitlements", "zip_export",
                "BOOLEAN DEFAULT FALSE", inspector)
    _add_column(db, "entitlements", "pdf_export",
                "BOOLEAN DEFAULT FALSE", inspector)
    _add_column(db, "entitlements", "custom_template_limit",
                "INTEGER DEFAULT 0", inspector)
    _add_column(db, "entitlements", "history_limit",
                "INTEGER DEFAULT 0", inspector)
    _add_column(db, "entitlements", "ai_credits",
                "INTEGER DEFAULT 0", inspector)
    _add_column(db, "entitlements", "ai_credits_used",
                "INTEGER DEFAULT 0", inspector)

    # ── Seed product plans ─────────────────────────────────────────────────
    import uuid

    _seed_plan(db, {
        "id": str(uuid.uuid4()),
        "name": "Free Teacher",
        "description": "For teachers exploring SchemeKnit — limited individual features.",
        "product_type": "subscription",
        "price": 0.0,
        "currency": "GHS",
        "duration_days": None,
        "seat_limit": 0,
        "features": "[]",
        "educational_levels": "[]",
        "template_access": "[]",
        "ai_access": "limited_trial",
        "content_access": "[]",
        "active": True,
        "created_at": now,
        "updated_at": now,
        "customer_type": "individual_teacher",
        "generation_limit": 5,
        "batch_generation": False,
        "zip_export": False,
        "pdf_export": True,
        "custom_template_limit": 1,
        "history_limit": 10,
        "ai_enabled": True,
        "ai_credits": 5,
        "max_generations_per_period": 5,
    }, inspector)

    _seed_plan(db, {
        "id": str(uuid.uuid4()),
        "name": "Teacher Pro",
        "description": "For individual teachers using SchemeKnit independently — full features.",
        "product_type": "subscription",
        "price": 49.0,
        "currency": "GHS",
        "duration_days": 30,
        "seat_limit": 0,
        "features": "[]",
        "educational_levels": "[]",
        "template_access": "[]",
        "ai_access": "full",
        "content_access": "[]",
        "active": True,
        "created_at": now,
        "updated_at": now,
        "customer_type": "individual_teacher",
        "generation_limit": 0,
        "batch_generation": True,
        "zip_export": True,
        "pdf_export": True,
        "custom_template_limit": 10,
        "history_limit": 100,
        "ai_enabled": True,
        "ai_credits": 50,
        "max_generations_per_period": 0,
    }, inspector)


def down(db):
    """SQLite doesn't support DROP COLUMN; no-op."""
    pass

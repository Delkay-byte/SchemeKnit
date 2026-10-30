"""Migration v040: Adesua/Kyerɛkyerɛni/Sukuu package labels and paid allowance.

Additive/updating only. Renames the sellable plans to the approved local package
names and records the PROPOSED 30-plan monthly allowance for individual plans.
Prices are not changed. School entitlements/seat/quota remain unchanged because
they are still awaiting commercial definition.
"""

from sqlalchemy.orm import Session  # noqa: F401

MIGRATION_VERSION = "v040_adesua_package_labels"
MIGRATION_NAME = "Adesua free package labels and individual paid allowance"

_RENAMES = {
    "teacher-monthly": "Kyerɛkyerɛni — Individual Teacher (Monthly)",
    "teacher-annual": "Kyerɛkyerɛni — Individual Teacher (Annual)",
    "school-monthly": "Sukuu — School (Monthly)",
}


def up(db):
    from ..database import SubscriptionPlanDB

    for slug, name in _RENAMES.items():
        plan = db.query(SubscriptionPlanDB).filter(
            SubscriptionPlanDB.slug == slug).first()
        if plan is None:
            continue
        plan.name = name
        if slug.startswith("teacher-"):
            ent = dict(plan.entitlements or {})
            ent["generation_limit"] = 30  # proposed; owner approval pending
            plan.entitlements = ent
    db.commit()


def down(db):
    pass

"""
Migration v014: Product brand migration (TeachFlow -> SchemeKnit).

Renames the persisted USER-FACING product plan value "TeachFlow School Annual"
to "SchemeKnit School Annual" and updates the two individual-plan descriptions
that mentioned the old brand. This is a data-only, idempotent migration.

Deliberately NOT touched (historical / technical):
  - platform_audit_logs (historical evidence, retained verbatim)
  - payments.product_name (recorded at purchase time; historical)
  - product_plans names that never carried the brand ("Free Teacher",
    "Teacher Pro", "Teacher Monthly/Annual", "School Monthly")
  - technical enum identifiers (FREE_TEACHER, TEACHER_PRO)
  - the teachflow_standard provenance string (persisted; the user-facing
    label changed in code, the value is retained for compatibility)

Rollback restores the previous user-facing values.
"""

from sqlalchemy import text

MIGRATION_VERSION = "v014_brand_migration_schemeknit"
MIGRATION_NAME = "Product Brand Migration (TeachFlow -> SchemeKnit)"

NAME_RENAMES = [
    ("TeachFlow School Annual", "SchemeKnit School Annual"),
]
DESCRIPTION_FIXES = [
    ("For teachers exploring TeachFlow - limited individual features.",
     "For teachers exploring SchemeKnit - limited individual features."),
    ("For individual teachers using TeachFlow independently - full features.",
     "For individual teachers using SchemeKnit independently - full features."),
]


def up(db):
    for old, new in NAME_RENAMES:
        result = db.execute(
            text("UPDATE product_plans SET name = :new WHERE name = :old"),
            {"old": old, "new": new},
        )
        if result.rowcount:
            print(f"v014: plan name '{old}' -> '{new}' ({result.rowcount} row(s))")

    for old, new in DESCRIPTION_FIXES:
        result = db.execute(
            text("UPDATE product_plans SET description = :new WHERE description = :old"),
            {"old": old, "new": new},
        )
        if result.rowcount:
            print(f"v014: plan description updated ({result.rowcount} row(s))")

    db.commit()


def down(db):
    for old, new in NAME_RENAMES:
        db.execute(
            text("UPDATE product_plans SET name = :old WHERE name = :new"),
            {"old": old, "new": new},
        )
    for old, new in DESCRIPTION_FIXES:
        db.execute(
            text("UPDATE product_plans SET description = :old WHERE description = :new"),
            {"old": old, "new": new},
        )
    db.commit()

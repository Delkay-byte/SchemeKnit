"""
Migration v030: repair corrupted JSON list fields on lesson_plans.

Production rows stored ``structured_references`` as a JSON-encoded STRING
(``"[]"`` double-encoded into ``'"[]"'``, or a string iterated into the
char list ``["[", "]"]``). Every export path crashed on those rows with a
pydantic ValidationError inside ``_db_to_lesson_model`` — surfaced as an
unhandled 500 with no CORS headers, so the browser reported a network
failure instead of the real error. The same corruption made the review UI
render split characters as fake references.

This repairs the four v023-era list fields (keywords, other_tlrs,
core_competencies, structured_references) back to canonical JSON lists.
The normalization runs in Python and the canonical check is driver-aware
(PostgreSQL json/jsonb columns arrive parsed; SQLite/TEXT columns arrive
as stored text), so the migration is dialect-portable (SQLite and
PostgreSQL) and idempotent: clean rows are detected as already-canonical
and never rewritten.

Reads are now defensive everywhere (``normalize_text_items`` /
``normalize_structured_references``); this migration persists the
canonical form so the stored data matches what every layer treats as
truth.
"""

import json
from sqlalchemy import text, inspect as sa_inspect
from sqlalchemy import JSON as sa_JSON
from ..ai_resource_text import normalize_text_items, normalize_structured_references

MIGRATION_VERSION = "v030_repair_json_list_fields"
MIGRATION_NAME = "Repair corrupted JSON list fields on lesson_plans"

#: Column -> canonicalizer. Only the v023 TEXT cohort: the fields whose
#: legacy storage mode is known to have produced serialized-string rows.
_FIELDS = {
    "keywords": normalize_text_items,
    "other_tlrs": normalize_text_items,
    "core_competencies": normalize_text_items,
    "structured_references": normalize_structured_references,
}


def _as_python(raw):
    """DB value -> python value (raw may be JSON text or an object)."""
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return raw
    return raw


def up(db):
    bind = db.get_bind()
    inspector = sa_inspect(bind)
    if not inspector.has_table("lesson_plans"):
        return

    all_cols = {c["name"]: c for c in inspector.get_columns("lesson_plans")}

    for col, canonicalize in _FIELDS.items():
        col_info = all_cols.get(col)
        if col_info is None:
            continue
        # Driver-aware canonical check. psycopg auto-parses PostgreSQL
        # json/jsonb columns, so rows come back as semantic Python values —
        # there a double-encoded '"[]"' reads back as the str "[]" and must
        # be compared against the repaired LIST (never against its JSON
        # text, or it would masquerade as canonical). SQLite and TEXT
        # columns hand back the stored JSON text, so those compare against
        # json.dumps(repaired).
        native_json = (
            bind.dialect.name == "postgresql"
            and isinstance(col_info["type"], sa_JSON)
        )
        rows = db.execute(text(f"SELECT id, {col} FROM lesson_plans")).fetchall()
        for row_id, raw in rows:
            repaired = canonicalize(_as_python(raw))
            if native_json:
                already_canonical = (raw == repaired)
            else:
                already_canonical = (raw == json.dumps(repaired))
            if already_canonical:
                continue
            db.execute(
                text(f"UPDATE lesson_plans SET {col} = :value WHERE id = :id"),
                {"value": json.dumps(repaired), "id": row_id},
            )
        db.commit()


def down(db):
    """Data repair is one-way; the canonical form is always re-derivable."""
    pass

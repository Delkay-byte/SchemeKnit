"""
Structured-reference integrity: the production export blocker.

Production lesson rows stored ``structured_references`` corrupted (a
double-encoded JSON string or a char-split list). Reading those rows raised
a pydantic ValidationError inside ``_db_to_lesson_model`` — an unhandled 500
with no CORS headers that killed every DOCX/PDF/XLSX/ZIP export.

These tests pin the three layers of the fix:
  1. ``normalize_structured_references`` canonicalizes every stored shape.
  2. The load path (export model + API serializer) survives corrupt rows.
  3. Migration v030 repairs the stored rows, dialect-portably and
     idempotently — and the write boundary refuses to re-corrupt them.
"""

import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from src.ai_resource_text import (
    normalize_structured_references,
    normalize_text_items,
)
from src.models import ReferenceEntry
from src.routers.generation import _db_to_lesson_model, _serialize_lesson


# ── 1. Normalizer ─────────────────────────────────────────────────────────

class TestNormalizeStructuredReferences:
    def test_none_and_non_list_shapes(self):
        assert normalize_structured_references(None) == []
        assert normalize_structured_references(5) == []
        assert normalize_structured_references({"title": "x"}) == []

    def test_double_encoded_empty_string(self):
        # The exact production corruption: stored '"[]"', read as "[]".
        assert normalize_structured_references("[]") == []

    def test_json_string_of_entries(self):
        raw = '[{"type": "Textbook", "title": "Core Maths"}]'
        assert normalize_structured_references(raw) == [
            {"type": "Textbook", "title": "Core Maths"}
        ]

    def test_char_split_garbage(self):
        # A string iterated into characters: list("[]").
        assert normalize_structured_references(["[", "]"]) == []
        assert normalize_structured_references(list('[{"title":"A"}]')) == [
            {"title": "A"}
        ]

    def test_mixed_junk_drops_unparseable_items(self):
        value = ["[", "]", {"title": "A"}, "1", None, 42]
        assert normalize_structured_references(value) == [{"title": "A"}]

    def test_clean_list_passes_through(self):
        entries = [{"type": "Other", "title": "B"}]
        assert normalize_structured_references(entries) == entries

    def test_pydantic_entries_pass_through(self):
        entry = ReferenceEntry(title="C")
        assert normalize_structured_references([entry]) == [entry]

    def test_plain_text_is_not_an_entry(self):
        assert normalize_structured_references("Photos, charts") == []

    def test_text_items_still_handle_serialized_strings(self):
        # The flat-string sibling field keeps its own canonical behaviour.
        assert normalize_text_items("[]") == []
        assert normalize_text_items('["a", "b"]') == ["a", "b"]


# ── 2. Load path survives corrupt rows ────────────────────────────────────

def _fake_lp(**overrides):
    base = dict(
        id="l1", scheme_id="s1", job_id="j1", week_number=1,
        week_ending=None, week_ending_derived=True, teaching_week=None,
        carry_forward=False, lesson_sequence=1, lesson_date=date(2026, 9, 14),
        lesson_number=1, period="Morning", class_level="Basic 9",
        subject="Science", class_size=24, duration_minutes=40,
        school_name="Test School", teacher_name="T",
        strand="Diversity of Matter", sub_strand="Materials",
        content_standard="B9.1.1.1", content_standard_code="B9.1.1.1",
        indicators=["B9.1.1.1.1 Identify materials"], indicator_codes=["B9.1.1.1.1"],
        lesson_topic="Matter", previous_knowledge="",
        wapef_deep_hope="", wapef_storyline="", wapef_through_lines=[],
        wapef_gods_story="", remarks="", learning_objectives=[],
        core_competencies=[], source_tlrs=[], other_tlrs=[],
        teaching_learning_resources=["Charts"], introduction="Intro",
        main_activities=[{"phase": "MAIN", "description": "Present."}],
        learner_activities=[], teacher_activities=[],
        assessment="Assess.", conclusion="Summarise.",
        references=[], structured_references=[], keywords=[],
        status="completed", ai_generated=False, teacher_edited=False,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class TestLoadPathSurvivesCorruptRows:
    @pytest.mark.parametrize("corrupt", [
        "[]",                      # double-encoded, read as this string
        '[{"title": "A"}]',        # JSON string of entries
        ["[", "]"],                # char-split empty
        list('[{"title":"A"}]'),   # char-split entries
        None,
    ])
    def test_db_to_lesson_model_never_raises(self, corrupt):
        model = _db_to_lesson_model(_fake_lp(structured_references=corrupt))
        for entry in model.structured_references:
            assert isinstance(entry, ReferenceEntry)

    def test_db_to_lesson_model_recovers_json_string_entries(self):
        model = _db_to_lesson_model(
            _fake_lp(structured_references='[{"title": "A"}]'))
        assert [r.title for r in model.structured_references] == ["A"]

    def test_db_to_lesson_model_keeps_valid_entries(self):
        model = _db_to_lesson_model(
            _fake_lp(structured_references=[{"type": "Textbook", "title": "B"}]))
        assert isinstance(model.structured_references[0], ReferenceEntry)
        assert model.structured_references[0].title == "B"

    @pytest.mark.parametrize("corrupt", [
        "[]", ["[", "]"], list('[{"title":"A"}]'),
    ])
    def test_serializer_never_emits_split_characters(self, corrupt):
        out = _serialize_lesson(_fake_lp(structured_references=corrupt))
        assert isinstance(out["structured_references"], list)
        for item in out["structured_references"]:
            assert item != "[" and item != "]"
        # Char-split garbage must not reach the review UI.
        assert out["structured_references"] in ([], [{"title": "A"}])


# ── 3. Write boundary + data repair ───────────────────────────────────────

from .conftest import make_user  # noqa: E402
from src.database import (  # noqa: E402
    LessonPlanDB, SchemeDB, GenerationJobDB, generate_id,
)


def _make_lesson(db, user, **overrides):
    scheme = SchemeDB(
        id=generate_id(), owner_id=user.id,
        filename="Basic 9 Science - Scheme.docx", subject="Science",
        class_level="Basic 9", term="First Term",
    )
    db.add(scheme)
    db.commit()
    job = GenerationJobDB(
        id=generate_id(), owner_id=user.id, scheme_id=scheme.id,
        status="completed", completed_lessons=1,
    )
    db.add(job)
    db.flush()
    fields = dict(
        id=generate_id(), job_id=job.id, owner_id=user.id, scheme_id=scheme.id,
        week_number=1, lesson_sequence=1, lesson_number=1,
        lesson_date=date(2026, 9, 14),
        class_level="Basic 9", subject="Science", class_size=24,
        duration_minutes=40, school_name="Test School", teacher_name="T",
        strand="Diversity of Matter", sub_strand="Materials",
        content_standard="B9.1.1.1", indicators=["B9.1.1.1.1 Identify materials"],
        lesson_topic="Matter", introduction="Intro",
        main_activities=[{"phase": "MAIN", "description": "Present."}],
        assessment="Assess.", conclusion="Summarise.",
        structured_references=overrides.pop("structured_references",
                                             [{"type": "Other", "title": "Ref"}]),
        keywords=overrides.pop("keywords", ["matter"]),
    )
    fields.update(overrides)
    lp = LessonPlanDB(**fields)
    db.add(lp)
    db.commit()
    db.refresh(lp)
    return lp


class TestWriteBoundaryCoercion:
    def test_string_structured_references_is_canonicalized(self, db):
        user = make_user(db)
        lp = _make_lesson(db, user)
        from src.service import data_service
        data_service.update_lesson_plan(
            db, lp.id, user.id,
            {"structured_references": "[]", "keywords": "matter, materials"},
        )
        db.refresh(lp)
        # No double-encoding: the stored value round-trips as a real list.
        assert lp.structured_references == []
        assert lp.keywords == ["matter", "materials"]

    def test_char_split_structured_references_is_dropped(self, db):
        user = make_user(db)
        lp = _make_lesson(db, user)
        from src.service import data_service
        data_service.update_lesson_plan(
            db, lp.id, user.id, {"structured_references": ["[", "]"]},
        )
        db.refresh(lp)
        assert lp.structured_references == []

    def test_non_list_activity_payload_is_refused(self, db):
        user = make_user(db)
        lp = _make_lesson(db, user)
        original = list(lp.main_activities)
        from src.service import data_service
        data_service.update_lesson_plan(
            db, lp.id, user.id, {"main_activities": "not-a-list"},
        )
        db.refresh(lp)
        assert lp.main_activities == original

    def test_valid_update_still_applies(self, db):
        user = make_user(db)
        lp = _make_lesson(db, user)
        from src.service import data_service
        refs = [{"type": "Textbook", "title": "Core Maths"}]
        data_service.update_lesson_plan(
            db, lp.id, user.id,
            {"structured_references": refs, "introduction": "New intro"},
        )
        db.refresh(lp)
        assert lp.structured_references == refs
        assert lp.introduction == "New intro"


class TestMigrationV030Repair:
    """The migration rewrites corrupted rows and leaves clean rows alone."""

    @staticmethod
    def _corrupt(db, lp, column, stored_value):
        db.execute(
            text(f"UPDATE lesson_plans SET {column} = :v WHERE id = :i"),
            {"v": stored_value, "i": lp.id},
        )
        db.commit()

    def test_repairs_double_encoded_structured_references(self, db):
        from src.migrations.v030_repair_json_list_fields import up
        user = make_user(db)
        lp = _make_lesson(db, user, structured_references=[])
        # The exact production value: JSON text encoding the string "[]".
        self._corrupt(db, lp, "structured_references", json.dumps("[]"))
        up(db)
        db.expire_all()
        db.refresh(lp)
        assert lp.structured_references == []

    def test_repairs_char_split_list(self, db):
        from src.migrations.v030_repair_json_list_fields import up
        user = make_user(db)
        lp = _make_lesson(db, user, structured_references=[])
        self._corrupt(db, lp, "structured_references", json.dumps(["[", "]"]))
        up(db)
        db.expire_all()
        db.refresh(lp)
        assert lp.structured_references == []

    def test_repairs_plain_text_keywords(self, db):
        from src.migrations.v030_repair_json_list_fields import up
        user = make_user(db)
        lp = _make_lesson(db, user, keywords=[])
        self._corrupt(db, lp, "keywords", "matter, materials")
        up(db)
        db.expire_all()
        db.refresh(lp)
        assert lp.keywords == ["matter", "materials"]

    def test_preserves_valid_entries_and_is_idempotent(self, db):
        from src.migrations.v030_repair_json_list_fields import up
        user = make_user(db)
        refs = [{"type": "Textbook", "title": "Kept"}]
        lp = _make_lesson(db, user, structured_references=refs)
        up(db)   # first run: nothing to repair
        db.expire_all()
        db.refresh(lp)
        assert lp.structured_references == refs
        up(db)   # second run: still nothing to repair
        db.expire_all()
        db.refresh(lp)
        assert lp.structured_references == refs


# ── 4. Unhandled errors must be readable cross-origin ─────────────────────

class TestUnhandledErrorCors:
    """ServerErrorMiddleware runs the generic Exception handler OUTSIDE
    CORSMiddleware — the handler must echo the origin itself or the browser
    reports an opaque network failure instead of the real error."""

    def _request(self, origin):
        from starlette.requests import Request
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/generation/x/download-url",
            "query_string": b"",
            "headers": [(b"origin", origin.encode())] if origin else [],
            "client": ("127.0.0.1", 1234),
            "server": ("test", 80),
        }
        return Request(scope)

    def test_allowed_origin_gets_cors_headers(self):
        import asyncio
        from src.config import get_settings
        from src.main import general_exception_handler
        allowed = get_settings().CORS_ORIGINS[0]
        resp = asyncio.run(
            general_exception_handler(self._request(allowed), RuntimeError("boom")))
        assert resp.status_code == 500
        assert resp.headers["access-control-allow-origin"] == allowed
        assert resp.headers["access-control-allow-credentials"] == "true"
        assert json.loads(resp.body) == {
            "error": True, "detail": "Internal server error",
        }

    def test_unknown_origin_gets_no_cors_headers(self):
        import asyncio
        from src.main import general_exception_handler
        resp = asyncio.run(
            general_exception_handler(
                self._request("https://evil.example"), RuntimeError("boom")))
        assert resp.status_code == 500
        assert "access-control-allow-origin" not in resp.headers

    def test_no_origin_gets_no_cors_headers(self):
        import asyncio
        from src.main import general_exception_handler
        resp = asyncio.run(
            general_exception_handler(self._request(None), RuntimeError("boom")))
        assert resp.status_code == 500
        assert "access-control-allow-origin" not in resp.headers

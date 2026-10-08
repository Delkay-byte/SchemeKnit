"""Priority 3 — Generate workflow API behaviour (§26).

The Generate page is being restructured around the teacher's mental model
(WEEKS → INDICATORS → GENERATE). The backend enablers those screens rely on
are pinned here, through the real endpoints:

  1. Occurrence-level selection: "[Generate lesson]" targets EXACTLY one
     source occurrence — one row of one source week — even when the same
     indicator code repeats across weeks (codes alone cannot express this).
  2. Stable lesson numbering: a lesson generated from a subset keeps the
     number the preview showed it, so per-lesson drafts keyed by
     ``lesson_sequence`` land on the right lesson (Scenario: partial
     generation with a pre-filled review row).
  3. Replacement, never duplication: regenerating a selection replaces those
     lessons in place; the scheme's lesson count stays stable (the old
     whole-scheme replace was dead code and a second run silently duplicated
     every lesson).
  4. Survivor semantics: lessons of weeks NOT regenerated — including teacher
     edits — survive byte-for-byte and are re-homed onto the current job so
     workspace/status/coverage/exports read one complete set.
  5. Quota stays distinct-code idempotent through the real endpoint:
     regenerating an already-counted code consumes nothing further.
"""

from __future__ import annotations

import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.database import LessonPlanDB, SchemeDB, WeekDB, generate_id  # noqa: E402
from src.models import TermConfig  # noqa: E402
from tests.conftest import make_user  # noqa: E402

REPEATED_CODE = "B7.1.1.1.1"
REPEATED_TEXT = "Identify the parts of a computer"


def _repeating_scheme(db, owner_id):
    """Two instruction weeks that repeat the SAME indicator code.

    Real schemes re-use a strand's indicator across weeks; occurrence ids
    (``week1:0:...`` vs ``week2:0:...``) are what keep the two copies
    distinct.
    """
    scheme = SchemeDB(
        id=generate_id(), owner_id=owner_id, filename="B7 Computing.docx",
        subject="ICT", class_level="Basic 7", term="First Term",
        academic_year="2026/2027", status="uploaded", detection_status="single",
    )
    db.add(scheme)
    db.flush()
    for n in (1, 2):
        db.add(WeekDB(
            id=generate_id(), scheme_id=scheme.id, week_number=n,
            start_date=date(2026, 9, 7), end_date=date(2026, 9, 11),
            week_type="instruction", strand="Introduction to Computing",
            sub_strand="Components of Computers and Computer Systems",
            content_standards=[f"B7.1.1.{n}"],
            indicators=[f"{REPEATED_CODE} {REPEATED_TEXT}"],
            resources=["Keyboard"],
        ))
    db.commit()
    return scheme


def _config(scheme_id):
    return TermConfig(
        scheme_of_work_id=scheme_id,
        term_start_date=date(2026, 9, 7), term_end_date=date(2026, 12, 18),
        lessons_per_week=2, lesson_duration_minutes=60, class_size=30,
        teaching_days=[0, 2], holidays=[], ai_mode="OFF",
        include_special_weeks=False,
        class_level="Basic 7", subject="ICT",
    )


def _app(db, user):
    from fastapi import FastAPI
    from src.auth import get_current_user, require_teacher_workflow
    from src.database import get_db
    from src.routers import generation as gen_router

    app = FastAPI()
    app.include_router(gen_router.router, prefix="/api/generation")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_teacher_workflow] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    return app


def _preview(client, scheme, config):
    resp = client.post(
        f"/api/generation/{scheme.id}/allocation-preview",
        json=config.model_dump(mode="json"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _generate(client, scheme, config, **extra):
    body = config.model_dump(mode="json")
    body.update(extra)
    resp = client.post(f"/api/generation/{scheme.id}/generate", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _scheme_lessons(client, scheme):
    resp = client.get(f"/api/generation/schemes/{scheme.id}/lessons")
    assert resp.status_code == 200, resp.text
    return resp.json()["lesson_plans"]


class TestOccurrenceSelection:
    """§26 B — generate ONE occurrence of a repeating indicator."""

    def test_single_occurrence_generates_exactly_that_lesson(self, db):
        from fastapi.testclient import TestClient

        user = make_user(db)
        scheme = _repeating_scheme(db, user.id)
        config = _config(scheme.id)

        with TestClient(_app(db, user)) as client:
            preview = _preview(client, scheme, config)
            rows = preview["lesson_review"]
            assert len(rows) == 2
            occ_by_week = {r["source_week"]: r["source_occurrence_id"]
                           for r in rows}
            assert occ_by_week[1] != occ_by_week[2]

            out = _generate(
                client, scheme, config,
                selected_occurrence_ids=[occ_by_week[2]],
                selected_indicator_codes=[REPEATED_CODE],
            )

            lessons = _scheme_lessons(client, scheme)
            assert len(lessons) == 1, "exactly one occurrence generated"
            lesson = lessons[0]
            assert lesson["source_occurrence_id"] == occ_by_week[2]
            assert lesson["week_number"] == 2
            assert out["generated_indicator_codes"] == [REPEATED_CODE]
            # Cumulative response totals match the persisted set.
            assert out["total_lessons"] == out["completed_lessons"] == 1

    def test_subset_keeps_the_preview_lesson_number(self, db):
        """Partial generation must not renumber (drafts key by sequence)."""
        from fastapi.testclient import TestClient

        user = make_user(db)
        scheme = _repeating_scheme(db, user.id)
        config = _config(scheme.id)

        with TestClient(_app(db, user)) as client:
            preview = _preview(client, scheme, config)
            rows = {r["source_week"]: r for r in preview["lesson_review"]}
            assert rows[1]["lesson_sequence"] == 1
            assert rows[2]["lesson_sequence"] == 2

            # A review draft saved for the SECOND row must land on the lesson
            # that preview called "2" — never on a renumbered "1".
            put = client.put(
                f"/api/generation/{scheme.id}/lesson-review",
                json={"drafts": {"2": {"period": "W2 marker"}}},
            )
            assert put.status_code == 200, put.text

            out = _generate(
                client, scheme, config,
                selected_occurrence_ids=[rows[2]["source_occurrence_id"]],
                selected_indicator_codes=[REPEATED_CODE],
            )
            lessons = _scheme_lessons(client, scheme)
            assert len(lessons) == 1
            assert lessons[0]["lesson_sequence"] == 2
            assert lessons[0]["period"] == "W2 marker"
            # The read-back the workspace does (job-scoped) sees the same set.
            job_lessons = client.get(
                f"/api/generation/{out['job_id']}/lessons"
            ).json()["lesson_plans"]
            assert [l["lesson_sequence"] for l in job_lessons] == [2]

    def test_unknown_occurrence_id_is_rejected(self, db):
        from fastapi.testclient import TestClient

        user = make_user(db)
        scheme = _repeating_scheme(db, user.id)
        config = _config(scheme.id)

        with TestClient(_app(db, user)) as client:
            resp = client.post(
                f"/api/generation/{scheme.id}/generate",
                json={**config.model_dump(mode="json"),
                      "selected_occurrence_ids": ["week99:0:nope"],
                      "selected_indicator_codes": [REPEATED_CODE]},
            )
            assert resp.status_code == 400
            assert "selected lessons could be found" in resp.json()["detail"]


class TestReplacementNeverDuplicates:
    """§26 — repeated generation of the same selection keeps counts stable."""

    def test_full_regeneration_replaces_without_duplicating(self, db):
        from fastapi.testclient import TestClient

        user = make_user(db)
        scheme = _repeating_scheme(db, user.id)
        config = _config(scheme.id)

        with TestClient(_app(db, user)) as client:
            preview = _preview(client, scheme, config)
            preview_sequences = sorted(
                r["lesson_sequence"] for r in preview["lesson_review"]
            )

            first = _generate(client, scheme, config)
            lessons = _scheme_lessons(client, scheme)
            assert len(lessons) == 2
            # Full generation matches preview numbering exactly (parity guard).
            assert sorted(l["lesson_sequence"] for l in lessons) == preview_sequences
            assert first["total_lessons"] == 2

            second = _generate(client, scheme, config)
            lessons_after = _scheme_lessons(client, scheme)
            assert len(lessons_after) == 2, "second full run must not duplicate"
            assert second["job_id"] != first["job_id"]
            assert second["total_lessons"] == 2

            # Quota: the scheme's ONE distinct code across both weeks, two
            # full runs — used stays 1 (regeneration is idempotent).
            assert second["quota"]["used"] == 1

    def test_occurrence_regeneration_replaces_only_that_lesson(self, db):
        from fastapi.testclient import TestClient

        user = make_user(db)
        scheme = _repeating_scheme(db, user.id)
        config = _config(scheme.id)

        with TestClient(_app(db, user)) as client:
            _generate(client, scheme, config)
            original = {l["week_number"]: l["id"]
                        for l in _scheme_lessons(client, scheme)}
            assert set(original) == {1, 2}

            preview = _preview(client, scheme, config)
            occ2 = {r["source_week"]: r["source_occurrence_id"]
                    for r in preview["lesson_review"]}[2]
            _generate(client, scheme, config,
                      selected_occurrence_ids=[occ2],
                      selected_indicator_codes=[REPEATED_CODE])

            lessons = _scheme_lessons(client, scheme)
            assert len(lessons) == 2, "regenerating week 2 replaced, not added"
            by_week = {l["week_number"]: l for l in lessons}
            assert by_week[1]["id"] == original[1], "week 1 untouched"
            assert by_week[2]["id"] != original[2], "week 2 regenerated"

            # And the idempotent quota never moved: the one distinct code of
            # this scheme re-reserved twice more, still exactly 1 unit used.
            assert _generate(
                client, scheme, config,
                selected_occurrence_ids=[occ2],
                selected_indicator_codes=[REPEATED_CODE],
            )["quota"]["used"] == 1


class TestSurvivorSemantics:
    """§26 — weeks outside the selection survive, edits included."""

    def test_teacher_edit_survives_and_moves_to_current_job(self, db):
        from fastapi.testclient import TestClient

        user = make_user(db)
        scheme = _repeating_scheme(db, user.id)
        config = _config(scheme.id)

        with TestClient(_app(db, user)) as client:
            _generate(client, scheme, config)
            week1 = next(l for l in _scheme_lessons(client, scheme)
                         if l["week_number"] == 1)
            week2 = next(l for l in _scheme_lessons(client, scheme)
                         if l["week_number"] == 2)

            # Teacher edits week 1's lesson directly (as save-lesson does).
            row = db.query(LessonPlanDB).filter(
                LessonPlanDB.id == week1["id"]
            ).one()
            row.teacher_edited = True
            row.remarks = "TEACHER-EDIT-MARKER"
            db.commit()

            preview = _preview(client, scheme, config)
            occ2 = {r["source_week"]: r["source_occurrence_id"]
                    for r in preview["lesson_review"]}[2]
            out = _generate(client, scheme, config,
                            selected_occurrence_ids=[occ2],
                            selected_indicator_codes=[REPEATED_CODE])

            lessons = _scheme_lessons(client, scheme)
            assert len(lessons) == 2
            by_week = {l["week_number"]: l for l in lessons}

            # Week 1: same row, edit intact, now visible under the new job.
            assert by_week[1]["id"] == week1["id"]
            assert by_week[1]["teacher_edited"] is True
            assert by_week[1]["remarks"] == "TEACHER-EDIT-MARKER"

            # Week 2: regenerated with stable numbering and the same identity.
            assert by_week[2]["source_occurrence_id"] == occ2
            assert by_week[2]["lesson_sequence"] == 2
            assert by_week[2]["id"] != week2["id"]

            # The current job's read-back (workspace/status/coverage/exports)
            # returns the complete merged set: survivor + regenerated lesson.
            job_lessons = client.get(
                f"/api/generation/{out['job_id']}/lessons"
            ).json()["lesson_plans"]
            assert sorted(l["week_number"] for l in job_lessons) == [1, 2]


class TestLegacyOccurrenceFallback:
    """Rows persisted before occurrence ids existed still replace safely."""

    def _unit(self, existing, occurrence_ids, chosen):
        from src.routers.generation import _replacement_ids_for_occurrences
        return _replacement_ids_for_occurrences(existing, occurrence_ids, chosen)

    def _lp(self, ident, week, occ="", codes=None):
        from types import SimpleNamespace
        return SimpleNamespace(
            id=ident, week_number=week, source_occurrence_id=occ,
            indicator_codes=codes if codes is not None else [REPEATED_CODE],
        )

    def _alloc(self, week, code=REPEATED_CODE):
        from types import SimpleNamespace
        return SimpleNamespace(week_number=week, indicator_code=code)

    def test_legacy_row_matches_week_and_code_only(self):
        # Chosen occurrence: week 2 of the repeated code.
        chosen = [self._alloc(2)]
        existing = [
            self._lp("modern-w1", 1, occ="week1:0:B7_1_1_1_1"),
            self._lp("modern-w2", 2, occ="week2:0:B7_1_1_1_1"),
            self._lp("legacy-w1", 1),   # no occurrence id
            self._lp("legacy-w2", 2),   # no occurrence id
        ]
        replaced = self._unit(existing, {"week2:0:B7_1_1_1_1"}, chosen)
        # Only week 2 rows die — the same code in week 1 survives.
        assert sorted(replaced) == ["legacy-w2", "modern-w2"]

    def test_legacy_codeless_row_matches_chosen_week_only(self):
        chosen = [self._alloc(2, code="")]
        existing = [
            self._lp("legacy-codeless-w1", 1, codes=[]),
            self._lp("legacy-codeless-w2", 2, codes=[]),
        ]
        replaced = self._unit(existing, {"week2:0:row"}, chosen)
        assert replaced == ["legacy-codeless-w2"]

"""
Pre-generation review drafts must reach the lesson the teacher configured.

The real defect: the allocation engine numbers allocations from 0 while
``build_lesson`` numbers the lessons it produces from 1. The lesson-review row
published the raw allocation index, the generate page keyed each row's WAPEF
selections / keywords / references by that index, and the generate endpoint then
looked the draft up by the lesson's 1-based sequence. Consequence in the browser:

* the FIRST row's WAPEF selections were applied to no lesson at all;
* every other row's selections were applied to the PREVIOUS lesson.

These tests pin the invariant: a review row's ``lesson_sequence`` is the number
the built lesson carries, and a draft saved against that number is applied to
that lesson and no other.
"""

from __future__ import annotations

import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.database import SchemeDB, WeekDB, generate_id  # noqa: E402
from src.engines.allocation_engine import AllocationEngine  # noqa: E402
from src.models import TermConfig  # noqa: E402
from src.routers.generation import (  # noqa: E402
    _apply_lesson_review_draft, preview_allocation,
)
from src.service import data_service  # noqa: E402
from tests.conftest import make_user  # noqa: E402


def _scheme(db, owner_id, weeks=3):
    scheme = SchemeDB(
        id=generate_id(), owner_id=owner_id, filename="B7 Computing.docx",
        subject="ICT", class_level="Basic 7", term="First Term",
        academic_year="2026/2027", status="uploaded", detection_status="single",
    )
    db.add(scheme)
    db.flush()
    for n in range(1, weeks + 1):
        db.add(WeekDB(
            id=generate_id(), scheme_id=scheme.id, week_number=n,
            start_date=date(2026, 9, 7), end_date=date(2026, 9, 11),
            week_type="instruction", strand="Introduction to Computing",
            sub_strand="Components of Computers and Computer Systems",
            content_standards=[f"B7.1.1.{n}"],
            indicators=[f"B7.1.1.{n}.1 Identify the parts of a computer"],
            resources=["Keyboard"],
        ))
    db.commit()
    return scheme


def _approved_hope(index: int = 0) -> str:
    """A real Deep Hope from the approved list (the only values that persist)."""
    from src.engines.wapef_fields import wapef_options

    options = wapef_options()["deep_hopes"]
    return options[index % len(options)]


def _built_lessons(db, scheme, config):
    """The lessons the generate endpoint would build for this scheme."""
    from src.routers.generation import pipeline, resolve_term_window

    engine = AllocationEngine()
    scheme_model = data_service.scheme_to_model(scheme)
    resolve_term_window(config, scheme_model.weeks)
    calendar = pipeline.calendar_engine.build_calendar(
        config, scheme_model.weeks, config.holidays)
    coverage = engine.allocate(
        scheme_model.weeks, calendar, config, config.include_special_weeks)
    return sorted(
        engine.generate_lesson_plans(coverage, config, scheme.id),
        key=lambda lp: lp.lesson_sequence,
    )


def _config(scheme_id):
    return TermConfig(
        scheme_of_work_id=scheme_id,
        term_start_date=date(2026, 9, 7), term_end_date=date(2026, 12, 18),
        lessons_per_week=2, lesson_duration_minutes=60, class_size=30,
        teaching_days=[0, 2], holidays=[], ai_mode="OFF",
        template_type="GES-style", include_special_weeks=False,
        class_level="Basic 7", subject="ICT",
    )


class TestReviewDraftAlignment:
    @pytest.mark.asyncio
    async def test_review_rows_use_the_number_the_built_lesson_carries(self, db):
        user = make_user(db)
        scheme = _scheme(db, user.id)
        report = await preview_allocation(scheme.id, _config(scheme.id), user, db)
        rows = report["lesson_review"]
        assert rows
        numbers = [r["lesson_sequence"] for r in rows]
        # 1-based and contiguous, exactly like the lessons build_lesson emits.
        assert numbers == list(range(1, len(rows) + 1)), numbers

    @pytest.mark.asyncio
    async def test_a_draft_reaches_exactly_the_lesson_it_was_keyed_to(self, db):
        user = make_user(db)
        scheme = _scheme(db, user.id)
        config = _config(scheme.id)
        report = await preview_allocation(scheme.id, config, user, db)
        rows = report["lesson_review"]
        assert len(rows) >= 2, "need at least two lessons for a shift to show"

        # The teacher configures the SECOND row only. Deep Hope values are
        # validated against the approved list, so a real option is used.
        hope = _approved_hope(0)
        second = rows[1]
        data_service.save_lesson_review_draft(
            db, scheme.id, user.id, str(second["lesson_sequence"]),
            {"wapef_deep_hope": hope, "keywords": ["input devices"]})

        plans = _built_lessons(db, scheme, config)
        assert len(plans) == len(rows)

        drafts = data_service.get_lesson_review_drafts(db, scheme.id, user.id)
        for lp in plans:
            _apply_lesson_review_draft(lp, drafts)

        first, chosen = plans[0], plans[1]
        # The configured row's lesson HAS the selections...
        assert chosen.wapef_deep_hope == hope, chosen.lesson_sequence
        assert chosen.keywords == ["input devices"]
        # ...and the lesson before it does NOT (the historical off-by-one).
        assert first.wapef_deep_hope == "", first.lesson_sequence
        assert "input devices" not in first.keywords, first.keywords

    @pytest.mark.asyncio
    async def test_the_first_rows_selections_are_not_dropped(self, db):
        user = make_user(db)
        scheme = _scheme(db, user.id)
        config = _config(scheme.id)
        report = await preview_allocation(scheme.id, config, user, db)
        rows = report["lesson_review"]

        hope = _approved_hope(1)
        first = rows[0]
        data_service.save_lesson_review_draft(
            db, scheme.id, user.id, str(first["lesson_sequence"]),
            {"wapef_deep_hope": hope, "keywords": ["first row keyword"]})

        plans = _built_lessons(db, scheme, config)
        drafts = data_service.get_lesson_review_drafts(db, scheme.id, user.id)
        for lp in plans:
            _apply_lesson_review_draft(lp, drafts)

        assert plans[0].wapef_deep_hope == hope
        assert plans[0].keywords == ["first row keyword"]

    @pytest.mark.asyncio
    async def test_a_draft_never_shifts_onto_the_neighbouring_lesson(self, db):
        """A key with no matching lesson must apply to NOTHING.

        An eager "sequence - 1" fallback would put one lesson's teacher
        additions onto the next lesson — the very off-by-one being fixed.
        """
        user = make_user(db)
        scheme = _scheme(db, user.id)
        plans = _built_lessons(db, scheme, _config(scheme.id))
        hope = _approved_hope(2)
        # Key "1" exists; the lesson numbered 2 has no draft of its own.
        drafts = {"1": {"wapef_deep_hope": hope}}
        for lp in plans:
            _apply_lesson_review_draft(lp, drafts)
        assert plans[0].wapef_deep_hope == hope
        assert plans[1].wapef_deep_hope == ""
        assert plans[2].wapef_deep_hope == ""


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))

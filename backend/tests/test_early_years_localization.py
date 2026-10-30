"""Early-years lessons must reach the Ghanaian context bank.

The localization bank has ``early_childhood`` and ``nursery`` entries, but the
assessment-context path is skipped for early years, so KG/Nursery lessons
never actually carried a local clause. These tests pin ONE bounded clause in
the real builder path for both profiles, with deterministic rotation across
weeks and no leakage into Basic-class lessons.
"""

from __future__ import annotations

import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.curriculum.activity_library import (  # noqa: E402
    GHANA_CONTEXT_BY_SUBJECT, ghana_context_for,
)
from src.curriculum.lesson_builder import build_lesson  # noqa: E402
from src.models import (  # noqa: E402
    AIMode, AllocatedIndicator, ClassLevel, Subject, TermConfig,
)


def _config(class_level):
    return TermConfig(
        scheme_of_work_id="probe", academic_year="2026/2027",
        term="First Term", class_level=class_level, subject=Subject.NUMERACY,
        term_start_date=date(2026, 9, 7), term_end_date=date(2026, 12, 18),
        lessons_per_week=1, lesson_duration_minutes=60, teaching_days=[0],
        holidays=[], ai_mode=AIMode.OFF, school_name="S", teacher_name="T",
    )


def _lesson(class_level, *, week=1, code_only=True):
    alloc = AllocatedIndicator(
        indicator_code="K2.1.1.1.1" if code_only else "K2.1.1.1.1",
        indicator_description="K2.1.1.1.1" if code_only else "Count and match objects",
        content_standard_code="K2.1.1.1", content_standard_description="",
        strand="Number", sub_strand="Counting and matching objects",
        week_number=week, source_resources=["bottle caps"],
        lesson_date=date(2026, 9, 7), period_index=1, allocated=True,
        teaching_week=week,
    )
    return build_lesson(alloc, _config(class_level), "probe")


def _lesson_text(lp):
    return " ".join([
        lp.lesson_topic or "",
        lp.introduction or "",
        lp.starter_activity or "",
        lp.assessment or "",
        lp.conclusion or "",
        " ".join(a.description for a in (lp.main_activities or [])),
        " ".join(a.description for a in (lp.learner_activities or [])),
    ])


@pytest.mark.parametrize(
    "class_level,profile_key",
    [(ClassLevel.KG1, "early_childhood"), (ClassLevel.NURSERY_1, "nursery")],
    ids=["kg", "nursery"],
)
def test_early_years_lesson_carries_one_bank_clause(class_level, profile_key):
    lp = _lesson(class_level)
    text = _lesson_text(lp)
    bank = GHANA_CONTEXT_BY_SUBJECT[profile_key]
    found = [clause for clause in bank if clause in text]
    assert len(found) == 1, (
        f"expected exactly one {profile_key} clause, found {found!r}")
    assert found[0] == ghana_context_for(profile_key, variant=1)


@pytest.mark.parametrize(
    "class_level,profile_key",
    [(ClassLevel.KG2, "early_childhood"), (ClassLevel.NURSERY_2, "nursery")],
    ids=["kg", "nursery"],
)
def test_context_rotates_across_weeks_without_repeating(
        class_level, profile_key):
    bank = GHANA_CONTEXT_BY_SUBJECT[profile_key]
    seen = []
    for week in (1, 2, 3):
        text = _lesson_text(_lesson(class_level, week=week))
        found = [clause for clause in bank if clause in text]
        assert len(found) == 1
        seen.append(found[0])
    assert len(set(seen)) == 3, f"three weeks must rotate: {seen!r}"


def test_basic_class_lesson_does_not_get_an_early_years_clause():
    lp = _lesson(ClassLevel.BASIC_2, code_only=False)
    text = _lesson_text(lp)
    for key in ("early_childhood", "nursery"):
        for clause in GHANA_CONTEXT_BY_SUBJECT[key]:
            assert clause not in text

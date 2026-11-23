"""WAPEF academic-year profile contract.

Deep Hope and Storyline are chosen ONCE per teacher per academic year and
reused on every WAPEF lesson. These tests pin:

* year isolation — a new year starts empty and never inherits older values;
* historical safety — saving a new year does not rewrite the old row;
* option validation — only approved values are stored;
* generation precedence — the annual values win over a conflicting per-lesson
  draft (the same guard that rejects conflicting AI output, because AI output
  is applied to the lesson before this final annual override);
* the missing-profile gate.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import wapef_annual  # noqa: E402
from src.database import WapefAnnualProfileDB  # noqa: E402
from src.engines.wapef_fields import (  # noqa: E402
    WAPEF_DEEP_HOPES, WAPEF_STORYLINES,
)
from src.models import LessonPlan  # noqa: E402
from src.routers.generation import (  # noqa: E402
    LessonConfigRequest, _apply_lesson_review_draft, _normalize_lesson_config,
)
from src.engines.lesson_quality_gate import wapef_loss_failures  # noqa: E402
from tests.conftest import make_user  # noqa: E402

DEEP_HOPE = WAPEF_DEEP_HOPES[0]
STORYLINE = WAPEF_STORYLINES[0]


def test_new_academic_year_starts_empty_and_preserves_history(db):
    user = make_user(db, email="wapef.annual@test.local")
    first = wapef_annual.save_profile(db, user.id, "2026/2027", DEEP_HOPE, STORYLINE)
    assert first["configured"] is True
    assert first["deep_hope"] == DEEP_HOPE

    # Opening the next year must NOT inherit the previous values.
    next_year = wapef_annual.get_profile(db, user.id, "2027/2028")
    assert next_year["configured"] is False
    assert next_year["deep_hope"] == ""
    assert next_year["storyline"] == ""
    assert next_year["missing"] == ["Deep Hope", "Storyline"]

    # And the historical row is untouched.
    prior = wapef_annual.get_profile(db, user.id, "2026/2027")
    assert prior["deep_hope"] == DEEP_HOPE
    assert prior["storyline"] == STORYLINE

    # Saving the new year cannot overwrite the old one either.
    wapef_annual.save_profile(db, user.id, "2027/2028", DEEP_HOPE, STORYLINE)
    rows = db.query(WapefAnnualProfileDB).filter(
        WapefAnnualProfileDB.teacher_id == user.id).all()
    assert len(rows) == 2
    prior = wapef_annual.get_profile(db, user.id, "2026/2027")
    assert prior["deep_hope"] == DEEP_HOPE


def test_zeli_gods_story_note_is_not_a_wapef_loss(db):
    user = make_user(db, email="wapef.gods.note@test.local")
    lp = LessonPlan(
        id="lp-gods-note",
        scheme_of_work_id="scheme-1",
        term_config_id="term-config-1",
        owner_id=user.id,
        subject="Science",
        class_level="Basic 4",
        week_number=1,
        lesson_sequence=0,
        lesson_date="2026-09-08",
        duration_minutes=60,
        template_id="tpl-wapef-approved-plan",
        generation_method="zeli",
        wapef_gods_story="Creation - All life belongs to God's good design. Genesis 1:27",
    )
    canonical = {"gods_story": "Creation"}
    assert wapef_loss_failures(lp, canonical) == []

    lp.generation_method = "standard"
    assert wapef_loss_failures(lp, canonical) == ["wapef_loss"]


def test_teacher_written_annual_values_are_preserved(db):
    user = make_user(db, email="wapef.annual.bad@test.local")
    saved = wapef_annual.save_profile(
        db, user.id, "2026/2027",
        "Our learners will care for creation.",
        "Walking faithfully in ordinary work.")
    assert saved["deep_hope"] == "Our learners will care for creation."
    assert saved["storyline"] == "Walking faithfully in ordinary work."
    assert saved["configured"] is True


def test_profile_required_before_wapef_generation(db):
    user = make_user(db, email="wapef.annual.missing@test.local")
    with pytest.raises(wapef_annual.WapefAnnualProfileMissing) as exc:
        wapef_annual.require_profile(db, user.id, "2026/2027")
    assert exc.value.missing == ["Deep Hope", "Storyline"]


def test_annual_values_beat_conflicting_per_lesson_draft(db):
    """A stale/AI-conflicting draft can never replace the year's values."""
    user = make_user(db, email="wapef.annual.wins@test.local")
    annual = wapef_annual.save_profile(
        db, user.id, "2026/2027", DEEP_HOPE, STORYLINE)
    lp = LessonPlan(
        id="lp-annual-wins",
        scheme_of_work_id="scheme-1",
        term_config_id="term-config-1",
        owner_id=user.id,
        subject="Mathematics",
        class_level="Basic 4",
        week_number=1,
        lesson_sequence=0,
        lesson_date="2026-09-08",
        duration_minutes=60,
    )
    drafts = {
        "0": {
            "wapef_deep_hope": "AI wrote a different hope",
            "wapef_storyline": "AI wrote a different storyline",
            "wapef_through_lines": ["Order discoverer"],
            "wapef_gods_story": "Creation",
        }
    }
    _apply_lesson_review_draft(lp, drafts, None, annual=annual)
    assert lp.wapef_deep_hope == DEEP_HOPE
    assert lp.wapef_storyline == STORYLINE
    # Topic-level fields still come from the teacher's per-lesson choice.
    assert lp.wapef_through_lines == ["Order discoverer"]
    assert lp.wapef_gods_story == "Creation"


def test_configuration_dialog_topic_choices_reach_the_lesson(db):
    """Through lines and God's Story selected in the dialog are applied."""
    from types import SimpleNamespace

    user = make_user(db, email="wapef.annual.topic@test.local")
    annual = wapef_annual.save_profile(
        db, user.id, "2026/2027", DEEP_HOPE, STORYLINE)
    lp = LessonPlan(
        id="lp-topic-wins",
        scheme_of_work_id="scheme-1",
        term_config_id="term-config-1",
        owner_id=user.id,
        subject="Mathematics",
        class_level="Basic 4",
        week_number=2,
        lesson_sequence=0,
        lesson_date="2026-09-15",
        duration_minutes=60,
        indicator_codes=["B4.1.1.1.3"],
        source_occurrence_id="week2:0:B4.1.1.1.3",
    )
    config = SimpleNamespace(indicator_wapef={
        "week2:0:B4.1.1.1.3": {
            "through_lines": ["Justice seeker", "Order discoverer"],
            "gods_story": "Redemption",
        },
    })
    _apply_lesson_review_draft(lp, {}, config, annual=annual)
    assert lp.wapef_through_lines == ["Justice seeker", "Order discoverer"]
    assert lp.wapef_gods_story == "Redemption"
    assert lp.wapef_deep_hope == DEEP_HOPE
    assert lp.wapef_storyline == STORYLINE


def test_indicator_wapef_is_normalized_and_validated():
    normalized, _sent_fields = _normalize_lesson_config(LessonConfigRequest(
        indicator_wapef={
            "week2:0:B4.1.1.1.3": {
                "through_lines": ["Justice seeker", "not approved"],
                "gods_story": "Redemption",
            },
        }
    ))
    assert normalized["indicator_wapef"] == {
        "week2:0:B4.1.1.1.3": {
            "through_lines": ["Justice seeker"],
            "gods_story": "Redemption",
        }
    }
    with pytest.raises(Exception):
        _normalize_lesson_config(LessonConfigRequest(
            indicator_wapef={"bad-key": {"through_lines": ["Order discoverer"]}}
        ))

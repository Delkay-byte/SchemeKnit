"""Regression tests for lesson completeness and WAPEF content quality.

These pin the defects reported on the Basic 4 Mathematics WAPEF scheme:

* a code-only indicator must never turn into the prose "B4";
* wrapped resource cells are rejoined, never printed as "patterns made from";
* code-only topics get topic-specific vocabulary (counting / operations /
  fractions) instead of one repeated list;
* Phase 1 text is not repeated in Phase 2, and drafting filler is removed;
* the DOCX download name is built from saved scheme metadata;
* a partially generated batch is reported as PARTIAL, not COMPLETED, and a
  retry generates only the missing unit without duplicating the saved one.
"""

from __future__ import annotations

import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.database import SchemeDB, WeekDB, generate_id  # noqa: E402
from src.models import LessonPlan, TermConfig  # noqa: E402
from tests.conftest import make_user  # noqa: E402


# ── WAPEF prose: code-only indicators ───────────────────────────────────────

@pytest.mark.parametrize("subject,class_prefix", [
    ("Mathematics", "B1"),
    ("Mathematics", "B4"),
    ("English", "B7"),
    ("Computing", "B9"),
])
def test_code_only_indicator_never_becomes_a_class_code(subject, class_prefix):
    from src.engines.wapef_connections import _focus_phrase, wapef_field_text

    lesson = {
        "subject": subject,
        "indicators": [f"{class_prefix}.1.1.1.1"],
        "sub_strand": "Counting, Representation & Cardinality",
        "strand": "Number",
    }
    focus = _focus_phrase(lesson)
    assert class_prefix.lower() not in focus.lower()
    assert "counting" in focus.lower()

    for field in ("through_lines", "gods_story", "storyline"):
        text = wapef_field_text(lesson, field)
        assert not f"with {class_prefix}" in text
        assert not f"with {class_prefix}." in text


def test_dotted_curriculum_codes_are_preserved_in_structured_fields():
    from src.engines.wapef_connections import _focus_phrase

    lesson = {
        "indicators": ["B4.1.1.1.1"],
        "sub_strand": "Fractions",
        "strand": "Number",
    }
    assert _focus_phrase(lesson) == "Fractions"


def test_throughline_keeps_the_teacher_selection_exactly():
    from src.engines.wapef_connections import wapef_field_text

    lesson = {
        "subject": "Mathematics",
        "indicators": ["B4.1.3.1.1"],
        "sub_strand": "Fractions",
        "strand": "Number",
        "wapef_through_lines": ["Order discoverer"],
    }
    text = wapef_field_text(lesson, "through_lines")
    assert text == "Order discoverer"
    assert "Fractions" not in text
    assert "with B4" not in text


# ── Resources ───────────────────────────────────────────────────────────────

def test_wrapped_resource_cell_is_rejoined_and_incomplete_labels_dropped():
    from src.curriculum.vocabulary import is_incomplete_resource
    from src.parsers.docx_parser import merge_wrapped_cell_lines

    merged = merge_wrapped_cell_lines(
        "Counters, bundle and loose straws base ten cut square, "
        "patterns made from\nManila cards,\nBundle of sticks")
    assert "patterns made from Manila cards" in merged
    assert "patterns made from\n" not in merged
    assert is_incomplete_resource("patterns made from")
    assert not is_incomplete_resource("patterns made from Manila cards")


def test_lesson_resource_lists_never_keep_a_dangling_fragment():
    from src.engines.lesson_content_quality import sanitize_resources

    lp = LessonPlan(
        term_config_id="t", week_number=1, lesson_sequence=1,
        lesson_date=date(2026, 9, 7),
        scheme_of_work_id="s", class_level="Basic 4", subject="Mathematics",
        source_tlrs=["Counters", "patterns made from"],
        teaching_learning_resources=["Counters", "patterns made from"],
    )
    sanitize_resources(lp)
    assert lp.source_tlrs == ["Counters"]
    assert lp.teaching_learning_resources == ["Counters"]


# ── Vocabulary ──────────────────────────────────────────────────────────────

def test_code_only_topic_vocabulary_changes_with_the_sub_strand():
    from src.curriculum.vocabulary import suggest_vocabulary

    counting = suggest_vocabulary(
        indicator="B4.1.1.1.1", content_standard="B4.1.1.1",
        sub_strand="Counting, Representation & Cardinality", strand="Number",
        subject="Mathematics")
    operations = suggest_vocabulary(
        indicator="B4.1.2.1.1", content_standard="B4.1.2.1",
        sub_strand="Number Operations", strand="Number", subject="Mathematics")
    fractions = suggest_vocabulary(
        indicator="B4.1.3.1.1", content_standard="B4.1.3.1",
        sub_strand="Fractions", strand="Number", subject="Mathematics")

    assert "counting" in {x.lower() for x in counting}
    assert "addition" in {x.lower() for x in operations}
    lower_fractions = {x.lower() for x in fractions}
    assert {"fraction", "fractions"} & lower_fractions
    assert {"numerator", "denominator", "whole"} <= lower_fractions
    assert counting != fractions


# ── Phase progression ───────────────────────────────────────────────────────

def _phase_lesson():
    return LessonPlan(
        term_config_id="t", week_number=1, lesson_sequence=1,
        lesson_date=date(2026, 9, 7),
        scheme_of_work_id="s", class_level="Basic 4", subject="Mathematics",
        source_occurrence_id="week1:0:B4.1.1.1.1",
        sub_strand="Fractions", strand="Number",
        lesson_topic="Fractions",
        starter_activity=(
            "Show a paper strip and ask learners to predict how many equal "
            "parts it will make."),
        introduction="This lesson focuses on fractions.",
        main_activities=[
            {"phase": "PHASE 1 · STARTER",
             "description": "Show a paper strip and ask learners to predict how many equal parts it will make.",
             "resources": []},
            {"phase": "DEMONSTRATION",
             "description": "Show a paper strip and ask learners to predict how many equal parts it will make. Model one half and name the numerator and denominator.",
             "resources": []},
            {"phase": "GUIDED PRACTICE",
             "description": "Learners fold strips into halves and quarters, then label numerator and denominator.",
             "resources": []},
            {"phase": "PHASE 3 · PLENARY",
             "description": "Learners state the same content in one sentence.",
             "resources": []},
        ],
        learner_activities=[
            {"phase": "PHASE 1 · STARTER",
             "description": "Learners write two predictions about the same content.",
             "resources": []},
            {"phase": "PHASE 2 · MAIN",
             "description": "Learners write two predictions about the same content. Learners label halves.",
             "resources": []},
        ],
        teacher_activities=[],
        conclusion="Learners state the same content in one sentence.",
    )


def test_starter_is_not_repeated_in_phase_two_and_filler_is_removed():
    from src.engines.lesson_content_quality import ensure_distinct_phases

    lp = _phase_lesson()
    ensure_distinct_phases(lp)

    def _desc(activity):
        return (activity.get("description") if isinstance(activity, dict)
                else activity.description) or ""

    phases = [(getattr(a, "phase", ""), _desc(a)) for a in lp.main_activities]
    demonstration = next(
        text for phase, text in phases if "DEMONSTRATION" in phase.upper())
    main = " ".join(text for _, text in phases).lower()
    assert "predict how many equal parts" not in demonstration.lower()
    assert "same content" not in main
    assert "same content" not in (lp.conclusion or "").lower()
    assert "numerator" in main


def test_phase_one_and_phase_two_keep_distinct_purposes():
    from src.engines.lesson_content_quality import ensure_distinct_phases

    lp = _phase_lesson()
    ensure_distinct_phases(lp)

    def _desc(activity):
        return (activity.get("description") if isinstance(activity, dict)
                else activity.description) or ""

    starter_rows = [
        _desc(a) for a in lp.main_activities
        if "STARTER" in (getattr(a, "phase", "") or "").upper()
    ]
    main_rows = [
        _desc(a) for a in lp.main_activities
        if "STARTER" not in (getattr(a, "phase", "") or "").upper()
        and "PLENARY" not in (getattr(a, "phase", "") or "").upper()
    ]
    assert starter_rows
    assert any("numerator" in row.lower() for row in main_rows)
    assert all(
        row.lower().strip() not in {s.lower().strip() for s in starter_rows}
        for row in main_rows
    )


def test_class_code_detection_ignores_dotted_curriculum_codes():
    from src.engines.lesson_content_quality import (
        class_code_prose_violations,
    )

    assert class_code_prose_violations("Learners work with B4.") == ["B4"]
    assert class_code_prose_violations(
        "Learning Indicator B4.1.1.1.1 and Content Standard B4.1.1.1"
    ) == []


# ── DOCX filename ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("term,class_level,subject,extension,expected", [
    ("First Term", "Basic 4", "Mathematics", "docx",
     "Term_1_Basic_4_Lesson_Plan_For_Mathematics.docx"),
    ("Second Term", "Basic 6", "English", "docx",
     "Term_2_Basic_6_Lesson_Plan_For_English.docx"),
    ("Third Term", "Basic 8", "Computing", "docx",
     "Term_3_Basic_8_Lesson_Plan_For_Computing.docx"),
    ("First Term", "KG 2", "Language and Literacy", "docx",
     "Term_1_KG_2_Lesson_Plan_For_Language_and_Literacy.docx"),
    ("Second Term", "JHS 1", "ICT", "pdf",
     "Term_2_JHS_1_Lesson_Plan_For_Computing.pdf"),
    ("Third Term", "SHS 2", "Science", "zip",
     "Term_3_SHS_2_Lesson_Plan_For_Science.zip"),
])
def test_docx_filename_is_built_from_scheme_metadata(
        term, class_level, subject, extension, expected):
    from src.routers.generation import lesson_plan_export_filename

    scheme = SchemeDB(
        id="s", owner_id="u", filename="whatever.docx", subject=subject,
        class_level=class_level, term=term,
    )
    assert lesson_plan_export_filename(scheme, extension) == expected


def test_docx_filename_never_contains_undefined_or_technical_values():
    from src.routers.generation import lesson_plan_export_filename

    scheme = SchemeDB(
        id="s", owner_id="u", filename="s.docx", subject="",
        class_level="", term="",
    )
    name = lesson_plan_export_filename(scheme, "docx")
    for bad in ("undefined", "null", "None", "s.docx"):
        assert bad not in name
    assert "_s_" not in name
    assert name.endswith(".docx")


# ── Partial generation end-to-end ───────────────────────────────────────────

def _partial_scheme(db, owner_id):
    scheme = SchemeDB(
        id=generate_id(), owner_id=owner_id, filename="Basic 4 Maths.docx",
        subject="Mathematics", class_level="Basic 4", term="First Term",
        academic_year="2026/2027", status="uploaded", detection_status="single",
    )
    db.add(scheme)
    db.flush()
    for n in (1, 2):
        db.add(WeekDB(
            id=generate_id(), scheme_id=scheme.id, week_number=n,
            start_date=date(2026, 9, 7), end_date=date(2026, 9, 11),
            week_type="instruction", strand="Number",
            sub_strand="Counting, Representation & Cardinality",
            content_standards=[f"B4.1.1.{n}"],
            indicators=[f"B4.1.1.{n}.1"],
            resources=["Counters"],
        ))
    db.commit()
    return scheme


def _partial_config(scheme_id):
    return TermConfig(
        scheme_of_work_id=scheme_id,
        term_start_date=date(2026, 9, 7), term_end_date=date(2026, 12, 18),
        lessons_per_week=1, lesson_duration_minutes=60, class_size=30,
        teaching_days=[0], holidays=[], ai_mode="OFF",
        include_special_weeks=False,
        class_level="Basic 4", subject="Mathematics",
    )


def _client(db, user):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.auth import get_current_user, require_teacher_workflow
    from src.database import get_db
    from src.routers import generation as gen_router

    app = FastAPI()
    app.include_router(gen_router.router, prefix="/api/generation")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_teacher_workflow] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_partial_generation_is_reported_and_retry_fills_only_the_missing_unit(
        db, monkeypatch):
    import src.routers.generation as gen
    from src.engines.lesson_quality_gate import LessonReport, summarize

    user = make_user(db)
    scheme = _partial_scheme(db, user.id)
    config = _partial_config(scheme.id)
    original_gate = gen._run_quality_gate

    def _one_missing(job, config, scheme_id, drafts, allow_rebuild=True, annual=None):
        report = original_gate(job, config, scheme_id, drafts,
                               allow_rebuild=allow_rebuild, annual=annual)
        accepted = list(report["accepted"])
        if len(accepted) > 1:
            dropped = accepted.pop()
            rejected = LessonReport(
                lesson_id=dropped.id,
                lesson_sequence=dropped.lesson_sequence,
                indicator_code=(dropped.indicator_codes[0]
                                if dropped.indicator_codes else ""),
                accepted=False,
                hard_failures=["forced_failure_for_partial_test"],
            )
            reports = list(report["reports"]) + [rejected]
            report = {
                "accepted": accepted,
                "reports": reports,
                "metrics": summarize(reports),
            }
        return report

    client = _client(db, user)
    monkeypatch.setattr(gen, "_run_quality_gate", _one_missing)
    body = config.model_dump(mode="json")
    first = client.post(f"/api/generation/{scheme.id}/generate", json=body)
    assert first.status_code == 200, first.text
    payload = first.json()
    assert payload["status"] == "partial"
    assert payload["total_lessons"] == 2
    assert payload["completed_lessons"] == 1
    assert len(payload["resumable_occurrence_ids"]) == 1
    missing = payload["resumable_occurrence_ids"][0]
    assert missing in payload["planned_occurrence_ids"]
    assert payload["lesson_units"]

    # Parent job status is honest on reload, not "completed".
    status = client.get(f"/api/generation/{payload['job_id']}/status").json()
    assert status["status"] == "partial"
    assert status["completed_lessons"] == 1

    # Retry only the missing unit.
    monkeypatch.setattr(gen, "_run_quality_gate", original_gate)
    second = client.post(
        f"/api/generation/{scheme.id}/generate/resume",
        json={"job_id": payload["job_id"]},
    )
    assert second.status_code == 200, second.text
    resumed = second.json()
    assert resumed["status"] == "completed"
    assert resumed["total_lessons"] == 2
    assert resumed["completed_lessons"] == 2
    assert resumed["generated_occurrence_ids"] == [missing]

    lessons = client.get(
        f"/api/generation/schemes/{scheme.id}/lessons").json()["lesson_plans"]
    assert len(lessons) == 2
    assert len({lp["source_occurrence_id"] for lp in lessons}) == 2

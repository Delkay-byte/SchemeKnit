"""
Pattern & Variation Quality Gate (Layers 3/4) — the 12 new checks
==================================================================

The quality gate was extended with twelve checks that make the pattern and
variation layers accountable: a lesson (or batch) that violates one FAILS the
gate rather than acquiring an arbitrary score deduction.

Nine checks run per lesson inside ``validate_lesson_quality``:
  1. phase_indicator_focus        — main phases name THIS indicator
  2. objective_indicator_alignment— objective points at THIS indicator
  3. phase_action_specificity     — concrete actions, never filler
  4. subject_specific_pedagogy    — no subject-agnostic placeholders
  5. pattern_subject_suitability  — selected pattern fits the subject
  7. filler_density               — no generic filler padding
  8. assessment_activity_alignment— assessment uses the indicator's verb
  9. assignment_alignment         — assignments are real, distinct tasks
 10. resource_alignment           — practical phases list resources

Three checks run across a batch inside ``validate_batch_variation``:
  6. batch_phase_repetition       — no identical phase sequences
 11. prior_lesson_continuity      — no duplicated consecutive focus
 12. batch_pattern_repetition / diversity / starter repetition
"""

import sys
sys.path.insert(0, '.')

from src.curriculum.quality_gate import (
    validate_lesson_quality,
    validate_batch_variation,
    QualityStatus,
)


def _lesson(**over):
    """A minimal, well-formed lesson dict that passes everything by default."""
    base = {
        "subject": "Mathematics",
        "indicator_codes": ["B7.1.1.1.1"],
        "duration_minutes": 60,
        "lesson_topic": "Add whole numbers",
        "indicators": ["B7.1.1.1.1 Add whole numbers"],
        "learning_objectives": [
            {"description": "Learners can add whole numbers accurately."},
        ],
        "starter_activity": (
            "Quick mental/oral drill: learners recall basic addition facts."),
        "main_activities": [
            {"phase": "Phase 1", "description": (
                "Teacher works through one worked example of adding whole "
                "numbers on the board, narrating each step.")},
            {"phase": "Phase 2", "description": (
                "Learners practise adding whole numbers in pairs using "
                "counters, then share one answer with the class.")},
            {"phase": "Phase 3", "description": (
                "Learners apply addition of whole numbers to solve a "
                "two-step word problem in their exercise books.")},
        ],
        "assessment": (
            "Learners solve three addition-of-whole-numbers questions and "
            "the teacher marks them against the success criteria."),
        "class_assignment": (
            "Learners complete five addition of whole numbers questions."),
        "home_assignment": (
            "Learners write and solve two real-life whole-number addition "
            "problems at home."),
        "teaching_learning_resources": ["counters", "exercise books"],
        "conclusion": (
            "Exit question: learners state one thing to check before adding "
            "whole numbers."),
        "pattern_id": "demonstrate_practice_apply",
    }
    base.update(over)
    return base


def _failures(lesson, indicator=None):
    return [i for i in validate_lesson_quality(lesson, indicator).failures]


def _warnings(lesson):
    return validate_lesson_quality(lesson).warnings


# ── Per-lesson checks ────────────────────────────────────────────────────────

def test_gate_passes_a_well_formed_lesson():
    report = validate_lesson_quality(_lesson())
    assert report.passed, [i.message for i in report.failures]


def test_check1_phases_must_reference_the_indicator_focus():
    """Rule: every rendered MAIN phase must be visibly about THIS indicator
    — a phase about 'the concept' with no link is a Layer-4 defect."""
    lesson = _lesson(main_activities=[
        {"phase": "Phase 1", "description": "Teacher explains the concept."},
        {"phase": "Phase 2", "description": "Learners practise the skill."},
        {"phase": "Phase 3", "description": "Learners complete the task."},
    ])
    names = [i.check_name for i in _warnings(lesson)]
    assert "phase_indicator_focus" in names


def test_check2_objective_must_point_at_the_indicator():
    """Rule: the objective references the indicator's own focus — a generic
    'Learners can work together' objective FAILS the gate."""
    lesson = _lesson(learning_objectives=[
        {"description": "Learners can work together in groups."}])
    failures = _failures(lesson)
    assert any(i.check_name == "objective_indicator_alignment" for i in failures)


def test_check3_bare_filler_phase_fails():
    """'Learners practise input devices' style filler is a hard failure —
    the phase-detail standard is part of the gate, not a suggestion."""
    lesson = _lesson(main_activities=[
        {"phase": "Phase 1", "description": "Learners practise input devices."},
    ])
    failures = _failures(lesson)
    assert any(i.check_name == "phase_action_specificity" for i in failures)


def test_check3_thin_phases_warn():
    """Terse but teacher-led phases are a warning, not a failure."""
    lesson = _lesson(main_activities=[
        {"phase": "Phase 1", "description": "Teacher explains the addition rule."},
        {"phase": "Phase 2", "description": "Teacher works one example."},
        {"phase": "Phase 3", "description": "Teacher sets practice questions."},
    ])
    names = [i.check_name for i in _warnings(lesson)]
    assert "phase_action_specificity" in names


def test_check4_subject_agnostic_placeholder_warns():
    """The MAIN phases must carry the subject's own pedagogy — placeholders
    like 'this topic' signal the Layer-2 pedagogy was bypassed."""
    lesson = _lesson(main_activities=[
        {"phase": "Phase 1", "description": (
            "Teacher introduces this topic with examples of whole numbers.")},
        {"phase": "Phase 2", "description": (
            "Learners discuss the concept in pairs and report back.")},
    ])
    names = [i.check_name for i in _warnings(lesson)]
    assert "subject_specific_pedagogy" in names


def test_check5_pattern_must_fit_the_subject():
    """An incompatible pattern is a selection defect. ``model_dump()`` keeps
    the Subject enum, so the gate must normalise it (regression guard)."""
    from src.models import Subject
    lesson = _lesson(subject=Subject.MATHEMATICS,
                     pattern_id="movement_demo_practice_perform")
    failures = _failures(lesson)
    assert any(i.check_name == "pattern_subject_suitability" for i in failures)


def test_check5_compatible_pattern_passes_and_enum_subject_is_normalised():
    from src.models import Subject
    lesson = _lesson(subject=Subject.MATHEMATICS,
                     pattern_id="demonstrate_practice_apply")
    assert not any(i.check_name == "pattern_subject_suitability"
                   for i in _failures(lesson))


def test_check5_unknown_pattern_warns():
    lesson = _lesson(pattern_id="no_such_pattern")
    names = [i.check_name for i in _warnings(lesson)]
    assert "pattern_subject_suitability" in names


def test_check7_no_pattern_is_not_an_error():
    """Single-lesson and early-years paths carry no pattern — the check must
    silently pass, not penalise play-based Nursery/KG lessons."""
    lesson = _lesson(pattern_id="")
    assert not any(i.check_name == "pattern_subject_suitability"
                   for i in _failures(lesson))


def test_check8_assessment_uses_the_indicator_verb():
    """An indicator asking learners to measure must not be assessed with
    copying-from-memory."""
    lesson = _lesson(
        indicator_codes=["B7.1.2.1.1"],
        indicators=["B7.1.2.1.1 Measure length using standard units"],
        learning_objectives=[{"description": (
            "Learners can measure length using standard units.")}],
        assessment="Learners copy the formula for perimeter into their books.")
    names = [i.check_name for i in _warnings(lesson)]
    assert "assessment_activity_alignment" in names


def test_check9_identical_class_and_home_assignments_fail():
    lesson = _lesson(class_assignment="Learners do the activity.",
                     home_assignment="Learners do the activity.")
    failures = _failures(lesson)
    assert any(i.check_name == "assignment_differentiation" for i in failures)


def test_check9_empty_assignment_warns():
    lesson = _lesson(home_assignment="")
    names = [i.check_name for i in _warnings(lesson)]
    assert "home_assignment_alignment" in names


def test_check10_practical_phase_without_resources_warns():
    """A lesson whose MAIN block is practical work but lists nothing on the
    table cannot be taught as written."""
    lesson = _lesson(main_activities=[
        {"phase": "Phase 1", "description": (
            "Learners investigate measuring instruments in groups and record "
            "their observations.")},
    ], teaching_learning_resources=[])
    names = [i.check_name for i in _warnings(lesson)]
    assert "resource_alignment" in names


def test_check10_discussion_phase_without_resources_is_fine():
    lesson = _lesson(main_activities=[
        {"phase": "Phase 1", "description": (
            "Learners discuss how whole numbers are used in daily life and "
            "share one example with the class.")},
    ], teaching_learning_resources=[])
    assert not any(i.check_name == "resource_alignment"
                   for i in _warnings(lesson))


# ── Batch checks ─────────────────────────────────────────────────────────────

def _batch(n=3, **over):
    lessons = []
    for i in range(n):
        lesson = _lesson(
            indicators=[f"B7.1.1.{i + 1}.1 Add whole numbers example {i}"],
            learning_objectives=[{"description": (
                f"Learners can add whole numbers example {i} accurately.")}],
            main_activities=[{"phase": "Phase 1", "description": (
                f"Teacher works through example {i} of adding whole numbers "
                f"on the board step by step.")}],
            starter_activity=f"Recall drill {i}: learners answer quick questions.",
            class_assignment=f"Learners complete example {i} in their books.",
            home_assignment=f"Learners make up example {i} at home.")
        for k, v in over.items():
            lesson[k] = v(lesson, i) if callable(v) else v
        lessons.append(lesson)
    return lessons


def test_batch_gate_passes_a_varied_batch():
    report = validate_batch_variation(_batch(3))
    assert report.passed, [i.message for i in report.failures]


def test_check6_identical_rendered_phases_fail_the_batch():
    """Cloned phase sequences across lessons — the core anti-repetition
    acceptance rule — FAIL the batch gate."""
    lessons = _batch(3)
    for lesson in lessons:  # identical mains, starters, pattern
        lesson["main_activities"] = [{"phase": "Phase 1", "description": (
            "Teacher works through one example on the board.")}]
        lesson["starter_activity"] = "Learners answer quick recall questions."
    report = validate_batch_variation(lessons)
    assert not report.passed
    names = {i.check_name for i in report.failures}
    assert "batch_main_repetition" in names
    assert "batch_starter_repetition" in names


def test_check12_constrained_reuse_is_not_flagged():
    """The same pattern reused with DIFFERENT rendered content is legitimate
    (constrained reuse) and must not fail the batch gate."""
    lessons = _batch(4, pattern_id="demonstrate_practice_apply")
    report = validate_batch_variation(lessons)
    assert not any(i.check_name == "batch_phase_repetition"
                   for i in report.failures)


def test_check12_one_pattern_for_a_whole_batch_warns():
    """A large batch locked onto a single teaching shape is a variation
    defect (warning — the shape may genuinely fit every indicator)."""
    lessons = _batch(8, pattern_id="demonstrate_practice_apply")
    report = validate_batch_variation(lessons)
    names = [i.check_name for i in report.issues]
    assert "batch_pattern_diversity" in names


def test_check11_duplicated_consecutive_focus_warns():
    """Two consecutive lessons carrying the identical indicator focus is a
    duplicated lesson — a continuity defect."""
    lessons = _batch(2)
    lessons[1]["indicators"] = lessons[0]["indicators"]
    report = validate_batch_variation(lessons)
    names = [i.check_name for i in report.issues]
    assert "prior_lesson_continuity" in names


def test_batch_gate_is_trivially_passing_for_a_single_lesson():
    assert validate_batch_variation([_lesson()]).passed
    assert validate_batch_variation([]).passed


# ── Integration: the gate is reachable from a real LessonPlan ────────────────

def test_validate_lesson_quality_accepts_a_model_dump():
    """The pipeline calls the gate with ``model_dump()``; the new checks must
    work on that shape (indicators list, enum subject, dict activities)."""
    from src.models import LessonPlan
    from datetime import date
    lp = LessonPlan(
        scheme_of_work_id="s", term_config_id="t",
        lesson_date=date(2026, 9, 29),
        week_number=1, day_number=1, lesson_sequence=1,
        subject="Mathematics", class_level="Basic 7",
        strand="Number", sub_strand="Number",
        indicators=["B7.1.1.1.1 Add whole numbers"],
        learning_objectives=[{"description": "Learners can add whole numbers."}],
        starter_activity="Learners recall basic addition facts.",
        main_activities=[{"phase": "Phase 1", "description": (
            "Teacher works through one whole-number addition example.")}],
        assessment="Learners solve three addition questions.",
        conclusion="Exit question: learners state one thing to check before adding.",
        class_assignment="Learners complete five addition questions.",
        home_assignment="Learners write two addition problems at home.",
        teaching_learning_resources=["counters"],
        core_competencies=[], essential_questions=[],
        keywords=[], lesson_objectives=[],
    )
    report = validate_lesson_quality(lp.model_dump())
    assert report.passed, [i.message for i in report.failures]

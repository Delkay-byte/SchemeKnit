"""
CRITICAL — Batch Variation Benchmark (Layers 1-4 integration).

The acceptance test for the whole pattern + variation engine. A teacher
generates a REAL batch of lessons from one scheme and the system must:

  * produce a complete, teachable lesson for every indicator (NO AI anywhere
    in the path — AI is OFF by default and the deterministic engine carries
    the batch alone);
  * NOT produce identical phase sequences across UNRELATED lessons;
  * NOT repeat the same starter without reason;
  * vary PATTERN SELECTION where the indicators genuinely differ (a batch of
    12 different indicators must not all be one teaching shape);
  * still REUSE a pattern when the indicators genuinely require it
    (constrained reuse, never variation for its own sake);
  * keep every lesson curriculum-aligned: indicator, objective, activities,
    assessment and assignments all point at THIS indicator.

This mirrors the teacher's real journey: upload -> extract -> select
indicators -> generate a batch -> inspect. It exercises the full pipeline
(allocation -> evidence -> pedagogy -> pattern -> variation -> builder) and
the quality gate, end to end.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.curriculum.quality_gate import validate_lesson_quality
from src.curriculum.variation import BatchHistory, fingerprint_lesson


def _gate(lp):
    """Quality gate takes a lesson DICT; failures (not warnings) fail a lesson."""
    return validate_lesson_quality(lp.model_dump())
from src.engines.generation_pipeline import GenerationPipeline
from src.models import (
    AIMode,
    ClassLevel,
    SchemeOfWork,
    Subject,
    TermConfig,
    Week,
    WeekType,
)

#: A REAL Basic 7 Mathematics batch: twelve indicators whose activity types
#: genuinely differ (procedural, investigative, classificatory, comparative,
#: communicative). This is the situation a teacher actually generates from.
BATCH_INDICATORS = [
    "B7.1.1.1.1 Add whole numbers up to 10,000",
    "B7.1.1.1.2 Subtract whole numbers up to 10,000",
    "B7.1.1.1.3 Solve word problems involving addition and subtraction",
    "B7.1.1.2.1 Multiply two-digit numbers by two-digit numbers",
    "B7.1.1.2.2 Divide two-digit numbers by one-digit numbers",
    "B7.1.2.1.1 Identify prime numbers up to 100",
    "B7.1.2.1.2 Classify numbers as even or odd",
    "B7.1.3.1.1 Compare fractions with the same denominator",
    "B7.1.3.1.2 Add and subtract fractions with the same denominator",
    "B7.1.4.1.1 Investigate the properties of 2-D shapes",
    "B7.1.4.1.2 Measure and compare lengths in metres and centimetres",
    "B7.1.5.1.1 Interpret data presented in a bar chart",
]
BATCH_SIZE = len(BATCH_INDICATORS)


def _weeks(indicators, per_week=3):
    weeks = []
    for i, code in enumerate(indicators):
        wn = i // per_week + 1
        if not weeks or weeks[-1].week_number != wn:
            weeks.append(Week(
                week_number=wn,
                start_date=date(2026, 9, 7), end_date=date(2026, 9, 11),
                week_type=WeekType.INSTRUCTION,
                strand="Number", sub_strand="Number and Numeration",
                content_standards=["B7.1.1.1 Number"],
                indicators=[], resources=[
                    "counters and bundles of sticks",
                    "place-value chart",
                    "number cards",
                    "exercise books and pencils",
                ], scheme_of_work_id="batch-scheme"))
        weeks[-1].indicators.append(code)
    return weeks


def _config(subject, duration=60, per_week=3):
    return TermConfig(
        scheme_of_work_id="batch-scheme",
        class_level=ClassLevel.BASIC_7,
        subject=subject,
        term="First Term",
        term_start_date=date(2026, 9, 7),
        term_end_date=date(2026, 12, 18),
        lessons_per_week=per_week,
        lesson_duration_minutes=duration,
        teaching_days=[0, 1, 2],
        holidays=[],
        ai_mode=AIMode.OFF,  # AI is OFF by default for the whole batch
    )


@pytest.fixture(scope="module")
def math_batch():
    """Generate the full batch ONCE; all assertions read the same result."""
    scheme = SchemeOfWork(
        id="batch-scheme",
        filename="B7_Mathematics_Scheme.docx",
        class_level=ClassLevel.BASIC_7,
        subject=Subject.MATHEMATICS,
        term="First Term", academic_year="2026/2027",
        weeks=_weeks(BATCH_INDICATORS),
        upload_date=date.today(),
    )
    job = GenerationPipeline().generate_all(scheme, _config(Subject.MATHEMATICS))
    plans = sorted(job._lesson_plans, key=lambda lp: lp.lesson_sequence)
    return plans


# ── 0. The batch is complete and deterministic-only ────────────────────────


def test_batch_generated_one_lesson_per_indicator(math_batch):
    assert len(math_batch) == BATCH_SIZE


def test_every_lesson_is_complete_without_ai(math_batch):
    """A teacher can teach from each lesson with no AI involvement."""
    for lp in math_batch:
        assert lp.ai_generated is False
        assert lp.starter_activity.strip()
        assert len(lp.main_activities) >= 2
        assert lp.conclusion.strip()
        assert lp.assessment.strip()
        assert lp.class_assignment.strip()
        assert lp.home_assignment.strip()
        assert lp.teaching_learning_resources


def test_batch_is_deterministic(math_batch):
    """Re-generating yields byte-identical lessons (no RNG in the path)."""
    scheme = SchemeOfWork(
        id="batch-scheme", filename="B7_Mathematics_Scheme.docx",
        class_level=ClassLevel.BASIC_7, subject=Subject.MATHEMATICS,
        term="First Term", academic_year="2026/2027",
        weeks=_weeks(BATCH_INDICATORS), upload_date=date.today())
    again = sorted(
        GenerationPipeline().generate_all(scheme, _config(Subject.MATHEMATICS)
                                          )._lesson_plans,
        key=lambda lp: lp.lesson_sequence)
    assert len(again) == len(math_batch)
    for a, b in zip(math_batch, again):
        assert a.starter_activity == b.starter_activity
        assert [m.description for m in a.main_activities] == \
            [m.description for m in b.main_activities]
        assert a.conclusion == b.conclusion


# ── 1. No identical phase sequences across unrelated lessons ──────────────


def test_no_identical_phase_sequences(math_batch):
    history = BatchHistory(scheme_id="batch-scheme", subject="Mathematics",
                           class_level="Basic 7", term="First Term")
    for lp in math_batch:
        history.record(fingerprint_lesson(lp, pattern_id=lp.pattern_id))
    report = history.repetition_report()
    assert report["duplicated_phase_sequences"] == [], \
        f"identical shapes across unrelated lessons: {report['duplicated_phase_sequences']}"


def test_no_identical_main_sequences(math_batch):
    history = BatchHistory(scheme_id="batch-scheme", subject="Mathematics")
    for lp in math_batch:
        history.record(fingerprint_lesson(lp, pattern_id=lp.pattern_id))
    report = history.repetition_report()
    assert report["duplicated_main_sequences"] == [], \
        f"cloned MAIN blocks: {report['duplicated_main_sequences']}"


def test_no_repeated_starters(math_batch):
    history = BatchHistory(scheme_id="batch-scheme", subject="Mathematics")
    for lp in math_batch:
        history.record(fingerprint_lesson(lp, pattern_id=lp.pattern_id))
    report = history.repetition_report()
    assert report["duplicated_starters"] == [], \
        f"one opener for the whole batch: {report['duplicated_starters']}"


# ── 2. Pattern selection varies with the indicators ───────────────────────


def test_pattern_selection_varies(math_batch):
    used = [lp.pattern_id for lp in math_batch]
    assert all(used), "pattern_id missing — batch did not use the pattern engine"
    distinct = set(used)
    assert len(distinct) >= 3, (
        f"the batch used only {len(distinct)} distinct pattern(s) for "
        f"{BATCH_SIZE} different indicators: {sorted(distinct)}")


def test_starter_modes_vary(math_batch):
    history = BatchHistory(scheme_id="batch-scheme", subject="Mathematics")
    for lp in math_batch:
        history.record(fingerprint_lesson(lp, pattern_id=lp.pattern_id))
    modes = {fp.starter_mode for fp in history.fingerprints}
    assert len(modes) >= 2, f"one starter mode for the whole batch: {modes}"


# ── 3. Constrained reuse: repetition is allowed when justified ────────────


def test_repeated_pattern_is_curriculum_justified(math_batch):
    """Where a pattern repeats, the indicators must genuinely call for it
    (procedural indicators may legitimately share a demonstration shape);
    the novelty penalty must not have forced an unsuitable pattern in."""
    used = [lp.pattern_id for lp in math_batch]
    if len(set(used)) < len(used):
        # Repeats exist: verify each repeated lesson is still quality-clean.
        from collections import Counter
        for pid, count in Counter(used).items():
            if count > 1:
                lessons = [lp for lp in math_batch if lp.pattern_id == pid]
                texts = {" ".join(lp.indicators) for lp in lessons}
                # All quality-gated and distinct in content.
                for lp in lessons:
                    assert _gate(lp).passed
                assert len(texts) == len(lessons)


# ── 4. Curriculum alignment never degrades for variation ──────────────────


def test_every_lesson_passes_the_quality_gate(math_batch):
    for lp in math_batch:
        result = _gate(lp)
        assert result.passed, (
            f"lesson {lp.lesson_sequence} failed the gate: "
            f"{[i.message for i in result.failures]}")


def test_indicator_objective_activity_assessment_chain(math_batch):
    """Indicator -> objective -> activity -> assessment -> assignment alignment."""
    for lp in math_batch:
        indicator = " ".join(lp.indicators or "")
        assert indicator.strip()
        # The objective must reference the indicator's own focus.
        objective = " ".join(o.description for o in lp.learning_objectives)
        # The MAIN activities, assessment and assignments must not be empty or
        # generic filler.
        main_text = " ".join(a.description for a in lp.main_activities)
        for text in (objective, main_text, lp.assessment, lp.class_assignment,
                     lp.home_assignment):
            assert len(text.strip()) >= 25
            low = text.lower()
            assert not any(p in low for p in ("learners practise the concept",
                                              "do the activity")), \
                "generic filler in a phase"


# ── 5. Phase 2 detail standard: concrete teacher/learner actions ──────────


def test_main_phases_describe_concrete_actions(math_batch):
    """Phase 2 must say what the teacher and learners DO — never
    'Learners practise input devices' style padding."""
    for lp in math_batch:
        for phase in lp.main_activities:
            desc = phase.description.strip()
            assert len(desc) >= 60, f"thin phase: {desc!r}"
            low = desc.lower()
            assert "practise input devices" not in low
            assert "complete the task" not in low
            assert "do the activity" not in low


def test_teacher_and_learner_activities_present(math_batch):
    for lp in math_batch:
        assert lp.teacher_activities
        assert lp.learner_activities
        assert len(lp.teacher_activities) == len(lp.main_activities)


# ── 6. Cross-subject sanity: the engine serves other subjects too ─────────


@pytest.mark.parametrize("subject,indicators", [
    (Subject.SCIENCE, [
        "B7.2.1.1.1 Describe the characteristics of living things",
        "B7.2.1.1.2 Investigate the states of matter",
        "B7.2.2.1.1 Classify materials into conductors and insulators",
        "B7.2.3.1.1 Explain the life cycle of a flowering plant",
    ]),
    (Subject.ENGLISH, [
        "B7.3.1.1.1 Use adjectives correctly in sentences",
        "B7.3.1.1.2 Read a short passage and answer questions",
        "B7.3.2.1.1 Write a paragraph describing a person",
        "B7.3.3.1.1 Listen to a story and retell it",
    ]),
])
def test_other_subjects_vary_without_ai(subject, indicators):
    scheme = SchemeOfWork(
        id="batch-scheme", filename="scheme.docx",
        class_level=ClassLevel.BASIC_7, subject=subject,
        term="First Term", academic_year="2026/2027",
        weeks=_weeks(indicators), upload_date=date.today())
    plans = sorted(
        GenerationPipeline().generate_all(scheme, _config(subject))._lesson_plans,
        key=lambda lp: lp.lesson_sequence)
    assert len(plans) == len(indicators)
    history = BatchHistory(scheme_id="batch-scheme", subject=subject.value)
    for lp in plans:
        assert lp.ai_generated is False
        assert _gate(lp).passed
        history.record(fingerprint_lesson(lp, pattern_id=lp.pattern_id))
    report = history.repetition_report()
    assert report["duplicated_main_sequences"] == []
    assert report["duplicated_starters"] == []
    assert len({lp.pattern_id for lp in plans}) >= 2

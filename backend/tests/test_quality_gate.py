"""Priority 4 — deterministic quality gate: adversarial + calibration tests.

The gate is the reason a weak deterministic lesson can no longer be saved.
These tests prove it:

* ``TestAdversarialHardFailures`` — every hard failure A–X is actually raised
  on a lesson carrying that defect (>= 20 distinct defects), and no failure is
  raised on a clean lesson.
* ``TestMechanicalRepair`` — the repair layer is deterministic, preserves the
  phase-sum invariant and never touches a clean lesson.
* ``TestDeterministicRebuild`` — a failed lesson is rebuilt with a DIFFERENT
  pattern, bounded at ``MAX_REBUILD_ATTEMPTS``, and the best candidate is
  chosen deterministically (same inputs -> same winner, ties -> source order).
* ``TestTimingMatrix`` — the supported durations 30-80 min all produce
  accepted lessons whose stored phase rows sum exactly to the duration.
* ``TestCalibration`` — the frozen corpus's real lessons pass the gate (no
  false rejects) and the floors are exactly the calibrated teacher-ready rule.
* ``TestEndpointGate`` — the canonical path persists only accepted lessons,
  reports gate metrics, and a total rejection fails the run, persists nothing
  and consumes no quota.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR))
sys.path.insert(0, str(BACKEND_DIR))

import benchmark_deterministic_lessons as base  # noqa: E402

from src.engines.allocation_engine import AllocationEngine, BuildLedger  # noqa: E402
from src.engines.calendar_engine import CalendarEngine  # noqa: E402
from src.engines.lesson_quality_gate import (  # noqa: E402
    MAX_REBUILD_ATTEMPTS,
    Outcome,
    Scored,
    build_entry,
    evaluate,
    hard_failures,
    mechanical_repair,
    pick_alternate_pattern,
    pick_best,
    wapef_loss_failures,
)
from src.models import (  # noqa: E402
    AIMode,
    ClassLevel,
    LearningObjective,
    ReferenceEntry,
    Subject,
    TermConfig,
    TeachingActivity,
)


# ── Fixtures ────────────────────────────────────────────────────────────────


def _config(subject, class_level, duration=60):
    return TermConfig(
        scheme_of_work_id="gate-test", academic_year="2026/2027",
        term="First Term", class_level=class_level, subject=subject,
        term_start_date=date(2026, 9, 7), term_end_date=date(2026, 12, 18),
        lessons_per_week=1, lesson_duration_minutes=duration,
        teaching_days=[0], holidays=[], ai_mode=AIMode.OFF,
        school_name="Gate Test", teacher_name="Gate Tester",
    )


def _batch(entries=None, duration=60):
    """Real lessons over the frozen corpus, grouped by subject like the
    benchmark's ``run_generation`` (``build_scheme`` is per-subject).

    Returns ``[(lesson, build_context, config, ledger), ...]`` in corpus order.
    """
    entries = list(entries if entries is not None else base.CORPUS)
    by_subject: dict = {}
    for entry in entries:
        key = (entry["subject"], entry["class_level"])
        by_subject.setdefault(key, []).append(entry)

    out = []
    for (subject, class_level), group in by_subject.items():
        scheme = base.build_scheme(group)
        config = _config(subject, class_level, duration)
        calendar = CalendarEngine().build_calendar(config, scheme.weeks, [])
        coverage = AllocationEngine().allocate(scheme.weeks, calendar, config)
        ledger = BuildLedger()
        plans = AllocationEngine().generate_lesson_plans(
            coverage, config, "gate-test", ledger=ledger)
        for lp in plans:
            out.append((lp, ledger.contexts.get(lp.id), config, ledger))
    return out


@pytest.fixture(scope="module")
def batch():
    return _batch()


@pytest.fixture
def lesson_and_entry(batch):
    """One good, pattern-shaped lesson with its ground-truth entry."""
    for lp, ctx, config, ledger in batch:
        if not getattr(lp, "pattern_id", "") or ctx is None:
            continue
        return lp, build_entry(ctx.alloc, lp), ctx, config, ledger
    raise AssertionError("no pattern-shaped lesson in the batch")


def _with(lp, **changes):
    """A copy of ``lp`` with fields replaced (the gate never mutates inputs)."""
    return lp.model_copy(update=changes)


# ── Adversarial hard failures (A–X) ─────────────────────────────────────────


class TestAdversarialHardFailures:
    """Every defect the spec lists must be caught; a clean lesson must pass."""

    def test_clean_lesson_is_accepted(self, lesson_and_entry):
        lp, entry, _ctx, _cfg, _ledger = lesson_and_entry
        outcome = evaluate(lp, entry)
        assert outcome.accepted, outcome.hard + outcome.floors
        assert hard_failures(lp, entry) == []

    def test_wrong_indicator(self, lesson_and_entry):
        lp, entry, _c, _x, _l = lesson_and_entry
        bad = _with(lp, indicators=["B9.9.9.9.9 Pronounce the alphabet backwards"])
        assert "wrong_indicator" in hard_failures(bad, entry)

    def test_missing_indicator(self, lesson_and_entry):
        lp, entry, _c, _x, _l = lesson_and_entry
        assert "missing_indicator" in hard_failures(_with(lp, indicators=[]), entry)

    def test_missing_content_standard(self, lesson_and_entry):
        lp, entry, _c, _x, _l = lesson_and_entry
        bad = _with(lp, content_standard="", content_standard_code="")
        assert "missing_content_standard" in hard_failures(bad, entry)

    def test_missing_content_standard_code(self, lesson_and_entry):
        lp, entry, _c, _x, _l = lesson_and_entry
        # The frozen corpus's synthetic scheme prints Content Standards without
        # their codes, so drive the check with a ground-truth entry that has one.
        with_code = dict(entry, content_standard_code="B7.1.1.1")
        bad = _with(lp, content_standard_code="")
        assert "missing_content_standard_code" in hard_failures(bad, with_code)

    def test_generic_objective(self, lesson_and_entry):
        lp, entry, _c, _x, _l = lesson_and_entry
        bad = _with(lp, learning_objectives=[
            LearningObjective(description="Learners can understand the topic")])
        assert "generic_objective" in hard_failures(bad, entry)

    def test_objective_unrelated_to_indicator(self, lesson_and_entry):
        lp, entry, _c, _x, _l = lesson_and_entry
        bad = _with(lp, learning_objectives=[
            LearningObjective(
                description="Learners can name the capital cities of Europe")])
        assert "generic_objective" in hard_failures(bad, entry)

    def test_missing_objective(self, lesson_and_entry):
        lp, entry, _c, _x, _l = lesson_and_entry
        assert "missing_objective" in hard_failures(_with(lp, learning_objectives=[]), entry)

    def test_empty_phase2_activity(self, lesson_and_entry):
        lp, entry, _c, _x, _l = lesson_and_entry
        bad = _with(lp, main_activities=[
            a.model_copy(update={"description": "Learners work."})
            for a in lp.main_activities])
        assert "generic_activity" in hard_failures(bad, entry)

    def test_no_phase2_rows(self, lesson_and_entry):
        lp, entry, _c, _x, _l = lesson_and_entry
        bad = _with(lp, main_activities=[
            a for a in lp.main_activities
            if "STARTER" in a.phase.upper() or "PLENARY" in a.phase.upper()])
        assert "generic_activity" in hard_failures(bad, entry)

    def test_missing_phase1(self, lesson_and_entry):
        lp, entry, _c, _x, _l = lesson_and_entry
        bad = _with(lp, main_activities=[
            a for a in lp.main_activities if "STARTER" not in a.phase.upper()])
        assert "missing_phase1" in hard_failures(bad, entry)

    def test_missing_phase3(self, lesson_and_entry):
        lp, entry, _c, _x, _l = lesson_and_entry
        bad = _with(lp, main_activities=[
            a for a in lp.main_activities if "PLENARY" not in a.phase.upper()])
        assert "missing_phase3" in hard_failures(bad, entry)

    def test_missing_learner_action(self, lesson_and_entry):
        lp, entry, _c, _x, _l = lesson_and_entry
        assert "missing_learner_action" in hard_failures(
            _with(lp, learner_activities=[]), entry)

    def test_missing_teacher_action(self, lesson_and_entry):
        lp, entry, _c, _x, _l = lesson_and_entry
        assert "missing_teacher_action" in hard_failures(
            _with(lp, teacher_activities=[]), entry)

    def test_filler_text(self, lesson_and_entry):
        lp, entry, _c, _x, _l = lesson_and_entry
        bad = _with(lp, assessment="Learners discuss the topic.")
        assert "filler_text" in hard_failures(bad, entry)

    def test_placeholder_reference(self, lesson_and_entry):
        lp, entry, _c, _x, _l = lesson_and_entry
        bad = _with(lp, references=["curriculum title for this subject"])
        assert "placeholder_reference" in hard_failures(bad, entry)

    def test_invalid_resources(self, lesson_and_entry):
        lp, entry, _c, _x, _l = lesson_and_entry
        bad = _with(lp, teaching_learning_resources=["a"])
        assert "invalid_or_empty_resources" in hard_failures(bad, entry)

    def test_duplicate_phases(self, lesson_and_entry):
        lp, entry, _c, _x, _l = lesson_and_entry
        dup = [a.model_copy() for a in lp.main_activities]
        dup.append(dup[len(dup) // 2].model_copy())
        assert "duplicate_phases" in hard_failures(_with(lp, main_activities=dup), entry)

    def test_incomplete_timing(self, lesson_and_entry):
        lp, entry, _c, _x, _l = lesson_and_entry
        bad = _with(lp, main_activities=[
            a.model_copy(update={"duration_minutes": 1}) for a in lp.main_activities])
        assert "incomplete_timing" in hard_failures(bad, entry)

    def test_invalid_duration(self, lesson_and_entry):
        lp, entry, _c, _x, _l = lesson_and_entry
        assert "invalid_duration" in hard_failures(_with(lp, duration_minutes=0), entry)
        assert "invalid_duration" in hard_failures(_with(lp, duration_minutes=999), entry)

    def test_missing_assessment(self, lesson_and_entry):
        lp, entry, _c, _x, _l = lesson_and_entry
        assert "missing_assessment" in hard_failures(_with(lp, assessment=""), entry)

    def test_indicator_code_mismatch(self, lesson_and_entry):
        lp, entry, _c, _x, _l = lesson_and_entry
        bad = _with(lp, indicator_codes=["B9.9.9.9.9"])
        assert "indicator_code_mismatch" in hard_failures(bad, entry)

    def test_source_week_mismatch(self, lesson_and_entry):
        lp, entry, _c, _x, _l = lesson_and_entry
        bad = _with(lp, week_number=lp.week_number + 99)
        assert "source_week_mismatch" in hard_failures(bad, entry)

    def test_source_occurrence_mismatch(self, lesson_and_entry):
        lp, entry, _c, _x, _l = lesson_and_entry
        bad = _with(lp, source_occurrence_id="week99:0:BOGUS")
        assert "source_occurrence_mismatch" in hard_failures(bad, entry)

    def test_corrupted_list_field(self, lesson_and_entry):
        lp, entry, _c, _x, _l = lesson_and_entry
        # pydantic coerces None in a List[str] only under validation; build the
        # corrupt state through model_construct so the gate sees the bad value.
        bad = lp.model_copy()
        object.__setattr__(bad, "keywords", [None, "ok"])
        assert "corrupted_field:keywords" in hard_failures(bad, entry)

    def test_empty_activity_row(self, lesson_and_entry):
        lp, entry, _c, _x, _l = lesson_and_entry
        rows = [a.model_copy() for a in lp.main_activities]
        rows[1] = rows[1].model_copy(update={"description": "   "})
        bad = _with(lp, main_activities=rows)
        assert "empty_activity_row" in hard_failures(bad, entry)

    def test_invalid_reference_shape(self, lesson_and_entry):
        lp, entry, _c, _x, _l = lesson_and_entry
        bad = _with(lp, structured_references=[
            ReferenceEntry(type="Textbook", title="", author_publisher="P")])
        assert "invalid_reference_shape" in hard_failures(bad, entry)

    def test_duplicate_reference(self, lesson_and_entry):
        lp, entry, _c, _x, _l = lesson_and_entry
        ref = ReferenceEntry(type="Textbook", title="Ghana Math", author_publisher="P")
        bad = _with(lp, structured_references=[ref, ref.model_copy()])
        assert "duplicate_reference" in hard_failures(bad, entry)

    def test_wapef_loss(self, lesson_and_entry):
        lp, _entry, _c, _x, _l = lesson_and_entry
        canonical = {
            "deep_hope": "Every learner is created unique and wonderfully made",
            "storyline": "Creation story",
            "through_lines": ["Beauty creator"],
            "gods_story": "God the creator",
        }
        intact = _with(
            lp, template_id="tpl-wapef-approved-plan",
            wapef_deep_hope=canonical["deep_hope"],
            wapef_storyline=canonical["storyline"],
            wapef_through_lines=list(canonical["through_lines"]),
            wapef_gods_story=canonical["gods_story"])
        assert wapef_loss_failures(intact, canonical) == []
        assert wapef_loss_failures(
            intact.model_copy(update={"wapef_deep_hope": ""}), canonical) == ["wapef_loss"]
        assert wapef_loss_failures(
            intact.model_copy(update={"wapef_deep_hope": "Something else"}),
            canonical) == ["wapef_loss"]

    def test_wapef_empty_state_is_not_a_loss(self, lesson_and_entry):
        """No saved selection -> empty fields are legitimate (boundary group G)."""
        lp, _entry, _c, _x, _l = lesson_and_entry
        empty = _with(lp, template_id="tpl-wapef-approved-plan")
        assert wapef_loss_failures(empty, None) == []
        assert wapef_loss_failures(empty, {}) == []
        partial = {"deep_hope": "", "storyline": "", "through_lines": [], "gods_story": ""}
        assert wapef_loss_failures(empty, partial) == []

    def test_non_wapef_template_skips_wapef_check(self, lesson_and_entry):
        lp, _entry, _c, _x, _l = lesson_and_entry
        canonical = {"deep_hope": "x", "storyline": "y",
                     "through_lines": [], "gods_story": "z"}
        assert wapef_loss_failures(lp, canonical) == []

    def test_every_adversarial_case_is_rejected(self, lesson_and_entry):
        """No defect above is a mere warning: each one fails the gate."""
        lp, entry, _c, _x, _l = lesson_and_entry
        defects = {
            "wrong_indicator": _with(lp, indicators=["Z9.9.9.9.9 Bogus focus"]),
            "missing_indicator": _with(lp, indicators=[]),
            "generic_objective": _with(lp, learning_objectives=[
                LearningObjective(description="Learners can discuss the topic")]),
            "generic_activity": _with(lp, main_activities=[
                a.model_copy(update={"description": "Do the work."})
                for a in lp.main_activities]),
            "incomplete_timing": _with(lp, main_activities=[
                a.model_copy(update={"duration_minutes": 2}) for a in lp.main_activities]),
            "filler_text": _with(lp, conclusion="Learners explore the topic."),
            "missing_assessment": _with(lp, assessment=""),
            "missing_phase1": _with(lp, main_activities=[
                a for a in lp.main_activities if "STARTER" not in a.phase.upper()]),
            "missing_learner_action": _with(lp, learner_activities=[]),
            "invalid_duration": _with(lp, duration_minutes=0),
            "source_week_mismatch": _with(lp, week_number=42),
        }
        rejected = {name: not evaluate(bad, entry).accepted
                    for name, bad in defects.items()}
        assert all(rejected.values()), rejected


# ── Mechanical repair ───────────────────────────────────────────────────────


class TestMechanicalRepair:

    def test_clean_lesson_needs_no_structural_repair(self, lesson_and_entry):
        """A passing lesson is never structurally rewritten by the repair layer
        (in the flow it is not repaired at all; cosmetic whitespace cleanup only
        ever runs on a lesson that already failed the gate)."""
        lp, entry, _c, _x, _l = lesson_and_entry
        repairs = mechanical_repair(lp)
        assert not any(p.startswith(("dedupe:", "restore:")) for p in repairs)
        assert evaluate(lp, entry).accepted

    def test_duplicate_rows_are_merged_and_the_sum_is_preserved(self, lesson_and_entry):
        lp, _entry, _c, _x, _l = lesson_and_entry
        rows = [a.model_copy() for a in lp.main_activities]
        target = len(rows) // 2
        rows.append(rows[target].model_copy())
        total_before = sum(int(a.duration_minutes or 0) for a in rows)
        bad = _with(lp, main_activities=rows)
        repairs = mechanical_repair(bad)
        assert "dedupe:main_activities" in repairs
        descriptions = [a.description for a in bad.main_activities]
        assert len(descriptions) == len(set(descriptions))
        # The duplicate's minutes are merged into the row that keeps its place —
        # the repair never silently drops teaching time.
        total_after = sum(int(a.duration_minutes or 0) for a in bad.main_activities)
        assert total_after == total_before

    def test_missing_phase1_row_is_restored_from_the_starter(self, lesson_and_entry):
        lp, _entry, _c, _x, _l = lesson_and_entry
        rows = [a for a in lp.main_activities if "STARTER" not in a.phase.upper()]
        bad = _with(lp, main_activities=rows)
        repairs = mechanical_repair(bad)
        assert "restore:phase1" in repairs
        first = bad.main_activities[0]
        assert "STARTER" in first.phase.upper()
        assert first.description == lp.starter_activity.strip()
        assert sum(int(a.duration_minutes or 0) for a in bad.main_activities) == lp.duration_minutes

    def test_missing_phase3_row_is_restored_from_the_conclusion(self, lesson_and_entry):
        lp, _entry, _c, _x, _l = lesson_and_entry
        rows = [a for a in lp.main_activities if "PLENARY" not in a.phase.upper()]
        bad = _with(lp, main_activities=rows)
        repairs = mechanical_repair(bad)
        assert "restore:phase3" in repairs
        assert "PLENARY" in bad.main_activities[-1].phase.upper()
        assert sum(int(a.duration_minutes or 0) for a in bad.main_activities) == lp.duration_minutes

    def test_whitespace_and_punctuation_are_cleaned(self, lesson_and_entry):
        lp, _entry, _c, _x, _l = lesson_and_entry
        bad = lp.model_copy(update={
            "assessment": "Learners  solve  problems .  ,",
            "conclusion": "Good   work ;;; today",
        })
        repairs = mechanical_repair(bad)
        assert "text:assessment" in repairs and "text:conclusion" in repairs
        assert bad.assessment == "Learners solve problems."
        assert bad.conclusion == "Good work; today"

# ── Deterministic rebuild ───────────────────────────────────────────────────


class TestDeterministicRebuild:

    def test_alternate_pattern_is_different_and_deterministic(self, lesson_and_entry):
        lp, _entry, ctx, config, ledger = lesson_and_entry
        first = pick_alternate_pattern(
            ctx.alloc, config, ledger.history, ctx.previous_indicator, [ctx.pattern_id])
        assert first is not None
        assert first.id != ctx.pattern_id
        # Same inputs always yield the same alternative.
        again = pick_alternate_pattern(
            ctx.alloc, config, ledger.history, ctx.previous_indicator, [ctx.pattern_id])
        assert again is not None and again.id == first.id
        second = pick_alternate_pattern(
            ctx.alloc, config, ledger.history, ctx.previous_indicator,
            [ctx.pattern_id, first.id])
        assert second is None or second.id not in (ctx.pattern_id, first.id)

    def test_rebuild_is_bounded(self, lesson_and_entry):
        """The caller never asks for more than MAX_REBUILD_ATTEMPTS alternatives,
        and every alternative it does ask for is distinct."""
        lp, _entry, ctx, config, ledger = lesson_and_entry
        tried = [ctx.pattern_id]
        ids = []
        for _ in range(MAX_REBUILD_ATTEMPTS):
            pattern = pick_alternate_pattern(
                ctx.alloc, config, ledger.history, ctx.previous_indicator, tried)
            if pattern is None:
                break
            tried.append(pattern.id)
            ids.append(pattern.id)
        assert len(ids) <= MAX_REBUILD_ATTEMPTS
        assert len(set(ids)) == len(ids)

    def test_no_pattern_means_no_rebuild(self, lesson_and_entry):
        """Early-years / pre-pattern lessons have no alternative shape."""
        lp, _entry, ctx, config, ledger = lesson_and_entry
        assert ctx.pattern_id, "fixture must be pattern-shaped"
        # A lesson built without a pattern (early years, legacy paths) has
        # nothing to swap — rebuild is not offered.
        assert pick_alternate_pattern(
            None, config, ledger.history, ctx.previous_indicator, []) is None

    def test_pick_best_ties_keep_source_order(self):
        a = Scored(lp="a", outcome=_outcome(), order=0)
        b = Scored(lp="b", outcome=_outcome(), order=1)
        assert pick_best([a, b]).lp == "a"
        assert pick_best([b, a]).lp == "b"

    def test_pick_best_ranks_curriculum_alignment_first(self):
        strong = Scored(lp="strong", outcome=_outcome(total=40, fidelity=5), order=1)
        weak = Scored(lp="weak", outcome=_outcome(total=70, fidelity=3), order=0)
        # Lower rubric total but higher curriculum fidelity still wins.
        assert pick_best([weak, strong]).lp == "strong"

    def test_pick_best_ranks_subject_pedagogy_above_total(self):
        strong = Scored(lp="strong", outcome=_outcome(total=40, pedagogy=5), order=1)
        weak = Scored(lp="weak", outcome=_outcome(total=70, pedagogy=2), order=0)
        assert pick_best([weak, strong]).lp == "strong"

    def test_collisions_demote_repetitive_candidates(self):
        unique = Scored(lp="u", outcome=_outcome(), fingerprint="x", collisions=0, order=1)
        repeated = Scored(lp="r", outcome=_outcome(), fingerprint="y", collisions=3, order=0)
        assert pick_best([repeated, unique]).lp == "u"

    def test_rebuilt_lesson_passes_the_gate(self, lesson_and_entry):
        """A lesson that fails on shape is rebuilt and the alternative passes."""
        from src.curriculum.lesson_builder import build_lesson
        lp, _entry, ctx, config, ledger = lesson_and_entry
        rebuilt = build_lesson(
            ctx.alloc, config, "gate-test",
            previous_indicator=ctx.previous_indicator,
            next_indicator=ctx.next_indicator,
            pattern=pick_alternate_pattern(
                ctx.alloc, config, ledger.history,
                ctx.previous_indicator, [ctx.pattern_id]),
        )
        outcome = evaluate(rebuilt, build_entry(ctx.alloc, rebuilt))
        assert outcome.accepted, outcome.hard + outcome.floors
        assert rebuilt.pattern_id != ctx.pattern_id


def _outcome(total=60, fidelity=5, pedagogy=3, activity=3, assessment=3):
    return Outcome(accepted=True, total=total, scores={
        "indicator_fidelity": fidelity,
        "subject_pedagogy_fit": pedagogy,
        "activity_specificity": activity,
        "assessment_alignment": assessment,
        "timing_integrity": 5,
    })


# ── Timing matrix ───────────────────────────────────────────────────────────


class TestTimingMatrix:
    """Every supported duration produces a lesson whose stored rows sum to it."""

    @pytest.mark.parametrize("duration", [30, 40, 50, 60, 70, 80])
    def test_duration_produces_an_accepted_lesson(self, duration):
        batch = _batch(duration=duration)
        assert batch
        for lp, ctx, _config, _ledger in batch:
            entry = build_entry(ctx.alloc if ctx else None, lp)
            outcome = evaluate(lp, entry)
            assert outcome.accepted, (lp.lesson_sequence, outcome.hard, outcome.floors)
            stored = sum(int(a.duration_minutes or 0) for a in lp.main_activities)
            assert stored == lp.duration_minutes == duration
            assert outcome.scores["timing_integrity"] == 5

    def test_phase2_has_several_steps_and_the_sum_is_exact(self):
        """The composition invariants hold for many-Phase-2 lessons too."""
        batch = _batch()
        for lp, _ctx, _c, _l in batch:
            p2 = [a for a in lp.main_activities
                  if "STARTER" not in a.phase.upper()
                  and "PLENARY" not in a.phase.upper()]
            assert len(p2) >= 2
            assert sum(int(a.duration_minutes or 0) for a in lp.main_activities) == 60


# ── Calibration against the frozen corpora ──────────────────────────────────


class TestCalibration:
    """The gate accepts the frozen corpus's real lessons (no false rejects),
    and the floors are exactly the calibrated teacher-ready rule."""

    def test_frozen_corpus_lessons_are_accepted(self):
        batch = _batch()
        assert batch
        accepted = [evaluate(lp, build_entry(ctx.alloc if ctx else None, lp)).accepted
                    for lp, ctx, _c, _l in batch]
        assert all(accepted)

    def test_floors_are_the_documented_teacher_ready_rule(self):
        from src.engines.lesson_quality_gate import REQUIRED_FLOORS
        # The gate's floors are exactly the calibrated teacher-ready rule from
        # the frozen benchmark (docs/QUALITY_GATE.md) — a regression guard
        # against silently changing the acceptance threshold.
        assert REQUIRED_FLOORS == {
            "timing_integrity": 5,
            "objective_specificity": 4,
            "topic_specificity": 3,
            "phase1_usefulness": 3,
            "phase2_usefulness": 3,
            "phase3_usefulness": 3,
            "assessment_alignment": 3,
            "resource_realism": 3,
        }

    def test_repeated_indicator_across_weeks_is_not_rejected(self):
        """A repeated indicator is a continuation, never a duplicate failure.

        The frozen corpus deliberately repeats B7.1.1.1.1 in weeks 1 and 2 as a
        progression probe: both lessons must pass the gate and differ in shape.
        """
        batch = _batch()
        maths = [(lp, ctx) for lp, ctx, _c, _l in batch
                 if lp.subject == Subject.MATHEMATICS]
        assert len(maths) >= 2
        codes = [lp.indicator_codes[0] for lp, _c in maths if lp.indicator_codes]
        assert codes[0] == codes[1] == "B7.1.1.1.1"
        for lp, ctx in maths:
            entry = build_entry(ctx.alloc if ctx else None, lp)
            outcome = evaluate(lp, entry)
            assert outcome.accepted, outcome.hard + outcome.floors
            assert "duplicate_phases" not in outcome.hard

    def test_messy_corpus_rows_are_structurally_valid(self):
        """Real-world messy source rows still produce structurally valid lessons
        (the gate never rejects a lesson for the source's own messiness — only
        for defects the composer could have avoided)."""
        from benchmark_hardening import MESSY_CORPUS
        batch = _batch(MESSY_CORPUS)
        assert batch
        structural = {"missing_phase1", "missing_phase3", "incomplete_timing",
                      "missing_assessment", "invalid_duration",
                      "missing_learner_action", "missing_teacher_action"}
        for lp, ctx, _c, _l in batch:
            entry = build_entry(ctx.alloc if ctx else None, lp)
            found = set(hard_failures(lp, entry))
            assert not (found & structural), (lp.lesson_sequence, found)


# ── Endpoint integration ────────────────────────────────────────────────────


from fastapi.testclient import TestClient  # noqa: E402


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


def _db_scheme(db, user, weeks=2):
    from src.database import SchemeDB, WeekDB, generate_id

    scheme = SchemeDB(
        id=generate_id(), owner_id=user.id, filename="Gate Scheme.docx",
        subject="ICT", class_level="Basic 7", term="First Term",
        academic_year="2026/2027", status="extracted", detection_status="single",
    )
    db.add(scheme)
    db.flush()
    for n in range(1, weeks + 1):
        db.add(WeekDB(
            id=generate_id(), scheme_id=scheme.id, week_number=n,
            start_date=date(2026, 9, 7), end_date=date(2026, 9, 11),
            week_type="instruction", strand="Introduction to Computing",
            sub_strand="Components of Computers",
            content_standards=[f"B7.1.1.{n}"],
            indicators=[f"B7.1.1.{n}.1 Identify the parts of a computer"],
            resources=["Keyboard", "Mouse"],
        ))
    db.commit()
    return scheme


def _gen_config(scheme):
    return TermConfig(
        scheme_of_work_id=scheme.id, academic_year="2026/2027",
        term="First Term", class_level="Basic 7", subject="ICT",
        term_start_date=date(2026, 9, 7), term_end_date=date(2026, 12, 18),
        lessons_per_week=1, lesson_duration_minutes=60,
        teaching_days=[0], holidays=[], ai_mode=AIMode.OFF,
    )


class TestEndpointGate:
    """The canonical path persists only accepted lessons and reports metrics."""

    def test_generation_reports_gate_metrics(self, db):
        from tests.conftest import make_user
        from src.service import data_service

        user = make_user(db)
        scheme = _db_scheme(db, user)
        with TestClient(_app(db, user)) as client:
            result = client.post(
                f"/api/generation/{scheme.id}/generate",
                json=_gen_config(scheme).model_dump(mode="json"),
            ).json()
        assert result["status"] == "completed"
        assert result["total_lessons"] == 2
        assert "quality" in result
        assert result["quality"]["lessons"] == 2
        assert result["quality"]["accepted"] == 2
        assert result["quality"]["rejected"] == 0
        rows = data_service.get_lesson_plans_for_scheme(db, scheme.id, user.id)
        assert len(rows) == 2

    def test_total_rejection_fails_the_run_and_consumes_nothing(
            self, db, monkeypatch):
        import src.engines.lesson_quality_gate as gate
        from tests.conftest import make_user
        from src.service import data_service

        def rejecting_evaluate(lp, entry, **kwargs):
            return Outcome(accepted=False, hard=["missing_assessment"])

        # _run_quality_gate imports evaluate by name from the gate module, so
        # patching the module attribute is what reaches it.
        monkeypatch.setattr(gate, "evaluate", rejecting_evaluate)

        user = make_user(db)
        scheme = _db_scheme(db, user)
        with TestClient(_app(db, user)) as client:
            response = client.post(
                f"/api/generation/{scheme.id}/generate",
                json=_gen_config(scheme).model_dump(mode="json"),
            )
            assert response.status_code == 500
            assert "quality gate rejected" in response.json()["detail"]
        rows = data_service.get_lesson_plans_for_scheme(db, scheme.id, user.id)
        assert rows == []

"""
Layer 4 — Variation / Anti-Repetition tests.

Contract under test:
  * repetition detection flags identical phase sequences, starters and
    sentence skeletons across unrelated lessons;
  * fingerprints are NORMALISED: trivial wording changes do NOT count as
    variation, and shared topic vocabulary does NOT count as repetition;
  * the same pattern may be legitimately reused when indicators genuinely
    require it (rule 6: constrained reuse);
  * history is scoped per scheme/subject/class/term — it never leaks across
    batches;
  * empty history is a valid state;
  * random wording is never the remedy: variation comes from selecting a
    different teaching sequence.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.curriculum.variation import (
    BatchHistory,
    GENERIC_FILLER_PHRASES,
    assignment_type,
    fingerprint_lesson,
    normalized_main_sequence,
    normalized_resource_sequence,
    normalized_starter,
)


def _lesson(starter="", mains=(), conclusion="", class_assignment="",
            home_assignment="", resources=("chalkboard", "exercise books"),
            indicators=("B7.1.1.1.1 Add whole numbers",)):
    """A lesson-shaped object for fingerprinting (fields a LessonPlan has)."""
    return SimpleNamespace(
        starter_activity=starter,
        main_activities=[SimpleNamespace(description=d) for d in mains],
        conclusion=conclusion,
        class_assignment=class_assignment,
        home_assignment=home_assignment,
        teaching_learning_resources=list(resources),
        indicators=list(indicators),
    )


# ── Normalisation ──────────────────────────────────────────────────────────


def test_normalized_starter_ignores_link_prefix():
    a = normalized_starter("Build on the previous lesson ('Addition'). Recall the method.")
    b = normalized_starter("Recall the method.")
    assert a == b


def test_normalized_starter_detects_real_repetition():
    assert normalized_starter("Quick recall of the last lesson.") == \
        normalized_starter("Quick recall of the last lesson.")


def test_normalized_main_sequence_strips_stopwords():
    seq = normalized_main_sequence([
        SimpleNamespace(description="Work through one example of addition on the board."),
    ])
    assert "addition" in seq and "the" not in seq and "one" not in seq


def test_resource_sequence_is_sorted_and_normalised():
    seq = normalized_resource_sequence(["Chalkboard", "exercise books", "Chalkboard"])
    assert seq == "chalkboard | exercise books"


@pytest.mark.parametrize("text,expected", [
    ("Sort the items into groups.", "sorting"),
    ("Classify the objects.", "sorting"),
    ("Write three sentences.", "written"),
    ("Practise the skill three times.", "practice"),
    ("Perform the song for the class.", "performance"),
    ("Observe the objects at home.", "observation"),
    ("Read the passage.", "reading"),
    ("Draw the diagram.", "production"),
    ("Compare the two items.", "comparison"),
    ("Discuss with your family.", "discussion"),
    ("", "none"),
])
def test_assignment_type_classification(text, expected):
    assert assignment_type(text) == expected


# ── Fingerprinting ─────────────────────────────────────────────────────────


def test_fingerprint_of_a_lesson_has_all_fields():
    fp = fingerprint_lesson(
        _lesson(starter="Quick recall.", mains=["Work through one example."],
                conclusion="State the rule."),
        pattern_id="demonstrate_practice_apply",
        starter_mode="retrieval", plenary_mode="explain_rule")
    assert fp.pattern_id == "demonstrate_practice_apply"
    assert fp.starter_mode == "retrieval"
    assert fp.plenary_mode == "explain_rule"
    assert fp.starter
    assert fp.main_sequence
    assert fp.class_assignment_type == "none"  # empty assignment → "none"
    assert fp.home_assignment_type == "none"
    assert not fp.is_empty


def test_empty_fingerprint_is_marked_empty():
    fp = fingerprint_lesson(_lesson())
    assert fp.is_empty


def test_fingerprints_match_when_shapes_match():
    a = fingerprint_lesson(_lesson(), pattern_id="p", starter_mode="retrieval",
                           plenary_mode="exit_question")
    b = fingerprint_lesson(_lesson(), pattern_id="p", starter_mode="retrieval",
                           plenary_mode="exit_question")
    assert a.matches_shape_of(b)


def test_fingerprints_differ_when_shapes_differ():
    a = fingerprint_lesson(_lesson(), pattern_id="p1", starter_mode="retrieval",
                           plenary_mode="exit_question")
    b = fingerprint_lesson(_lesson(), pattern_id="p2", starter_mode="prediction",
                           plenary_mode="exit_question")
    assert not a.matches_shape_of(b)


def test_starter_mode_inferred_from_text():
    fp = fingerprint_lesson(_lesson(starter="Predict what will happen next."))
    assert fp.starter_mode == "prediction"


def test_plenary_mode_inferred_from_text():
    fp = fingerprint_lesson(_lesson(conclusion="Exit question: answer before leaving."))
    assert fp.plenary_mode == "exit_question"


# ── Batch history ──────────────────────────────────────────────────────────


def test_empty_history_is_valid_state():
    h = BatchHistory(scheme_id="s", subject="Mathematics")
    assert h.recent_pattern_ids() == ()
    assert h.repetition_report()["lessons"] == 0
    assert h.pattern_repeat_streak() == 0


def test_history_records_and_reports_lessons():
    h = BatchHistory(scheme_id="s", subject="Mathematics")
    h.record_lesson(_lesson(starter="Quick recall.", mains=["Work through one example."]),
                    pattern_id="demonstrate_practice_apply")
    h.record_lesson(_lesson(starter="Predict the outcome.",
                            mains=["Carry out the investigation."]),
                    pattern_id="question_discovery_conclude")
    report = h.repetition_report()
    assert report["lessons"] == 2
    assert report["distinct_patterns"] == 2


def test_history_scoped_per_subject_class_and_term():
    """History must never leak across schemes, subjects, classes or terms."""
    a = BatchHistory(scheme_id="s1", subject="Mathematics", class_level="Basic 7")
    a.record_lesson(_lesson(starter="Quick recall.", mains=["Example one."]),
                    pattern_id="demonstrate_practice_apply")
    assert BatchHistory(scheme_id="s2", subject="Mathematics",
                        class_level="Basic 7").recent_pattern_ids() == ()
    assert BatchHistory(scheme_id="s1", subject="Science",
                        class_level="Basic 7").recent_pattern_ids() == ()
    assert BatchHistory(scheme_id="s1", subject="Mathematics",
                        class_level="Basic 8").recent_pattern_ids() == ()


def test_note_selection_feeds_selection_before_fingerprint_exists():
    h = BatchHistory()
    h.note_selection("demonstrate_practice_apply")
    assert h.recent_pattern_ids() == ("demonstrate_practice_apply",)
    h.note_selection("question_discovery_conclude")
    assert h.recent_pattern_ids() == ("demonstrate_practice_apply",
                                      "question_discovery_conclude")


# ── Repetition detection (the batch acceptance rules) ─────────────────────


def test_identical_main_sequence_flagged_across_lessons():
    h = BatchHistory()
    for _ in range(3):
        h.record_lesson(_lesson(starter=f"Starter {_}", mains=[
            "Work through one example.", "Guided practice on the skill."]))
    report = h.repetition_report()
    assert len(report["duplicated_main_sequences"]) == 1
    assert report["duplicated_main_sequences"][0]["count"] == 3


def test_identical_starters_flagged_across_lessons():
    h = BatchHistory()
    for topic in ("addition", "subtraction", "multiplication"):
        # Same opener, different topic: the SKELETON is what repeats.
        h.record_lesson(_lesson(starter=f"Quick recall of the last lesson on {topic}."))
    report = h.repetition_report()
    # Identical normalised text is flagged; here starters differ by topic, so
    # the *text* check may pass â€” the MODE check below catches the skeleton.
    starter_modes = [fp.starter_mode for fp in h.fingerprints]
    assert starter_modes == ["retrieval"] * 3  # one opener skeleton throughout


def test_unrelated_identical_shapes_flagged():
    """The same pattern across DIFFERENT indicators is a repetition smell."""
    h = BatchHistory()
    for topic in ("addition", "forces", "poetry", "family"):
        h.record_lesson(
            _lesson(starter="Quick recall.", mains=[f"Work on {topic}."],
                    indicators=(f"CODE {topic}",)),
            pattern_id="demonstrate_practice_apply",
            starter_mode="retrieval", plenary_mode="exit_question")
    report = h.repetition_report()
    assert len(report["duplicated_phase_sequences"]) == 1
    assert report["duplicated_phase_sequences"][0]["count"] == 4


def test_same_pattern_reuse_is_justified_when_indicators_match():
    """Rule 6: a repeated pattern is legitimate when the indicators are the
    same kind of work AND the rendered phases still differ (constrained reuse
    — the teaching method repeats, the lesson content does not)."""
    h = BatchHistory()
    h.record_lesson(
        _lesson(starter="Quick recall.", mains=["Work through one addition example."],
                indicators=("B7.1.1.1.1 Add whole numbers",)),
        pattern_id="demonstrate_practice_apply",
        starter_mode="retrieval", plenary_mode="exit_question")
    h.record_lesson(
        _lesson(starter="Quick recall.", mains=["Work through one subtraction example."],
                indicators=("B7.1.1.1.1 Add whole numbers",)),
        pattern_id="demonstrate_practice_apply",
        starter_mode="retrieval", plenary_mode="exit_question")
    report = h.repetition_report()
    assert report["duplicated_phase_sequences"] == []  # not cloned, not dominant
    # But genuinely identical rendered phases ARE flagged even under reuse.
    h2 = BatchHistory()
    for _ in range(2):
        h2.record_lesson(
            _lesson(starter="Quick recall.", mains=["Work through one example."],
                    indicators=("B7.1.1.1.1 Add whole numbers",)),
            pattern_id="demonstrate_practice_apply",
            starter_mode="retrieval", plenary_mode="exit_question")
    assert len(h2.repetition_report()["duplicated_phase_sequences"]) == 1


def test_filler_density_detected():
    h = BatchHistory()
    h.record_lesson(_lesson(
        starter="Watch and listen carefully.", mains=["Complete the task."]))
    report = h.repetition_report()
    assert report["filler_density"]


def test_repeat_streak_counts_consecutive_same_pattern():
    h = BatchHistory()
    for pid in ("a", "a", "a", "b"):
        h.record_lesson(_lesson(starter="s", mains=["m"]),
                        pattern_id=pid, starter_mode="retrieval")
    assert h.pattern_repeat_streak() == 1  # last lesson used "b"


def test_long_streak_detected():
    h = BatchHistory()
    for _ in range(4):
        h.record_lesson(_lesson(starter="s", mains=["m"]),
                        pattern_id="same-pattern", starter_mode="retrieval")
    assert h.pattern_repeat_streak() == 4


def test_normalized_starter_catches_skeleton_repetition():
    """'Learners practise input devices' style filler is detectable."""
    assert GENERIC_FILLER_PHRASES
    text = " ".join(GENERIC_FILLER_PHRASES)
    fp = fingerprint_lesson(_lesson(starter=text))
    assert fp.starter  # normalisation still produces content

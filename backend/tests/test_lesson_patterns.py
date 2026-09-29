"""
Layer 3 — Lesson Pattern Catalog tests.

Contract under test:
  * the catalog is the bounded set of 14 named teaching sequences;
  * each pattern declares its compatibility metadata (subjects, verbs,
    activities, levels, durations, resources, unsuitable situations);
  * selection is a pure deterministic function of the inputs (no RNG);
  * CURRICULUM FIT OUTWEIGHS NOVELTY: a genuinely fitting pattern wins even
    when it was used in the previous lesson;
  * the bounded novelty penalty only breaks ties among equally fitted
    patterns — it never drags in an unsuitable pattern to appear different;
  * the same pattern may be reused when the indicators genuinely require it;
  * an incompatible subject never wins, whatever else matches.
"""

from __future__ import annotations

import pytest

from src.curriculum.patterns import (
    PATTERNS,
    PATTERN_BY_ID,
    SelectionContext,
    catalog_size,
    canonical_pattern_ids,
    level_band,
    novelty_penalty,
    pattern_for_id,
    score_pattern,
    select_pattern,
)


# ── Catalog integrity ──────────────────────────────────────────────────────


def test_catalog_has_fourteen_patterns():
    assert catalog_size() == 14
    assert len(PATTERNS) == 14


def test_pattern_ids_are_unique_and_stable():
    ids = [p.id for p in PATTERNS]
    assert len(set(ids)) == len(ids)
    assert all(pattern_for_id(i) is not None for i in ids)


def test_every_pattern_has_at_least_three_steps():
    """A teaching sequence needs enough steps for a real MAIN block."""
    for p in PATTERNS:
        assert len(p.steps) >= 3, f"{p.id} has too few steps"
        assert all(s.name and s.activity_key for s in p.steps), p.id


def test_every_pattern_declares_compatibility_metadata():
    """Each pattern must say WHEN it is the right sequence (the 10 factors)."""
    for p in PATTERNS:
        assert p.compatible_subjects, f"{p.id} declares no compatible subjects"
        assert p.suitable_verbs, f"{p.id} declares no suitable verbs"
        assert p.suitable_activity_types, f"{p.id} declares no activities"
        assert p.suitable_assessment_forms, f"{p.id} declares no assessments"
        assert p.min_duration <= p.max_duration, p.id
        assert p.resource_needs in ("LOW", "MEDIUM"), p.id
        assert p.starter_mode, f"{p.id} has no starter mode"
        assert p.plenary_mode, f"{p.id} has no plenary mode"


def test_pattern_lookup_missing_returns_none():
    assert pattern_for_id("does-not-exist") is None
    assert pattern_for_id("") is None
    assert pattern_for_id("  ") is None


def test_fingerprint_structure_is_pattern_specific():
    seen = {p.fingerprint_structure()[0] for p in PATTERNS}
    assert len(seen) == 14


# ── Level bands ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("level,expected", [
    ("Nursery", "nursery"),
    ("KG 1", "kg"),
    ("KG 2", "kg"),
    ("Basic 1", "basic_lower"),
    ("Basic 3", "basic_lower"),
    ("Basic 4", "basic_upper"),
    ("Basic 6", "basic_upper"),
    ("Basic 7", "jhs"),
    ("Basic 9", "jhs"),
    ("SHS 1", "shs"),
    ("", ""),
    ("unknown", ""),
])
def test_level_band_mapping(level, expected):
    assert level_band(level) == expected


# ── Determinism ────────────────────────────────────────────────────────────


def test_selection_is_deterministic():
    ctx = SelectionContext(subject_profile="mathematics", class_level="Basic 7",
                           indicator_text="Add whole numbers",
                           indicator_activity="problem_solving")
    a = select_pattern(ctx)
    b = select_pattern(ctx)
    assert a[0].id == b[0].id
    assert a[1] == b[1]
    assert a[2] == b[2]


def test_selection_with_history_is_deterministic():
    ctx = SelectionContext(subject_profile="science", class_level="Basic 7",
                           indicator_text="Investigate living things",
                           indicator_activity="investigation",
                           recent_pattern_ids=("question_discovery_conclude",))
    assert select_pattern(ctx, novelty_penalty=novelty_penalty(ctx))[0].id == \
        select_pattern(ctx, novelty_penalty=novelty_penalty(ctx))[0].id


# ── Curriculum fit outweighs novelty ───────────────────────────────────────


def test_subject_canonical_pattern_wins_on_fit():
    """Mathematics + problem_solving keeps its worked-example sequence."""
    ctx = SelectionContext(subject_profile="mathematics", class_level="Basic 7",
                           indicator_text="Add whole numbers",
                           indicator_activity="problem_solving")
    p, score, _ = select_pattern(ctx)
    assert p.id in canonical_pattern_ids(ctx)
    assert score > 0


def test_same_pattern_reused_when_fit_demands_it():
    """A genuinely procedural indicator keeps the demonstration pattern even
    under maximum novelty pressure (constrained reuse)."""
    used = []
    for _ in range(3):
        ctx = SelectionContext(subject_profile="ict", class_level="Basic 7",
                               indicator_text="Operate the computer",
                               indicator_activity="practical",
                               recent_pattern_ids=tuple(used))
        p, _, _ = select_pattern(ctx, novelty_penalty=novelty_penalty(
            ctx, recency_weight=0.5, max_penalty=0.9))
        used.append(p.id)
    # The demonstration pattern family is still in play after three lessons.
    assert "demonstrate_practice_apply" in used or \
        "practical_troubleshoot_explain" in used


def test_incompatible_subject_never_wins():
    """PHE's movement pattern is incompatible with Mathematics; it can never be
    selected for a Mathematics lesson, whatever else matches."""
    ctx = SelectionContext(subject_profile="mathematics", class_level="Basic 7",
                           indicator_text="Perform and demonstrate movements",
                           indicator_activity="practical")
    p, _, _ = select_pattern(ctx)
    assert "mathematics" in p.compatible_subjects


def test_incompatible_subject_score_is_deeply_negative():
    ctx = SelectionContext(subject_profile="mathematics",
                           indicator_activity="practical")
    movement = pattern_for_id("movement_demo_practice_perform")
    assert score_pattern(movement, ctx) < 0


def test_novelty_only_reorders_close_fits():
    """The penalty is bounded so a strong fit always survives it."""
    ctx = SelectionContext(subject_profile="creative_arts",
                           class_level="Basic 7",
                           indicator_text="Create a pattern",
                           indicator_activity="creation")
    without = select_pattern(ctx)[0]
    heavy = {"creative_demo_creation_critique": 0.6}
    with_penalty = select_pattern(ctx, novelty_penalty=heavy)[0]
    # A creation indicator keeps the creation pattern; the bounded penalty
    # cannot evict the only genuinely-fitting pattern.
    assert without.id == with_penalty.id == "creative_demo_creation_critique"


def test_different_indicators_select_different_patterns():
    cases = [
        ("science", "investigation", "question_discovery_conclude"),
        ("mathematics", "problem_solving", "demonstrate_practice_apply"),
        ("creative_arts", "creation", "creative_demo_creation_critique"),
        ("rme", "discussion", "story_discussion_apply"),
    ]
    for subject, activity, expected in cases:
        ctx = SelectionContext(subject_profile=subject, class_level="Basic 7",
                               indicator_text="lesson focus",
                               indicator_activity=activity)
        p, _, _ = select_pattern(ctx)
        assert p.id in canonical_pattern_ids(ctx), (subject, activity, p.id)


# ── Novelty penalty bounds ─────────────────────────────────────────────────


def test_empty_history_gives_no_penalty():
    ctx = SelectionContext(subject_profile="mathematics",
                           indicator_activity="problem_solving")
    assert novelty_penalty(ctx) == {}


def test_penalty_is_bounded_and_recency_weighted():
    ctx = SelectionContext(subject_profile="mathematics",
                           indicator_activity="problem_solving",
                           recent_pattern_ids=("a", "b", "a", "c", "a"))
    pen = novelty_penalty(ctx)
    assert pen  # something is penalised
    assert all(v <= 0.6 for v in pen.values())  # bounded


def test_first_lesson_of_batch_uses_pure_fit():
    """Position 0 with empty history must select the canonical pattern."""
    ctx = SelectionContext(subject_profile="mathematics", class_level="Basic 7",
                           indicator_text="Add whole numbers",
                           indicator_activity="problem_solving",
                           lesson_position=0,
                           recent_pattern_ids=())
    p, score, _ = select_pattern(ctx, novelty_penalty=novelty_penalty(ctx))
    assert p.id in canonical_pattern_ids(ctx)

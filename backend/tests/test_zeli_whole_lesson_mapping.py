"""Whole-lesson Zeli mapping contracts.

These tests pin the differences between OPTIONAL AI enrichment (which must
preserve the deterministic curriculum scaffold) and the "Generate with Zeli"
method (where the provider writes the whole lesson and its own teaching moves
must survive the mapping).

They are regression tests for defects found during the first real DeepSeek
generation run: generic scaffold teacher/learner columns, irrelevant scaffold
resources, lost prior knowledge, deterministic provenance on AI objectives,
and invented starter/plenary minutes.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from src.engines.generation_pipeline import GenerationPipeline  # noqa: E402
from src.engines.zeli_generation import zeli_lesson_context  # noqa: E402
from src.models import (  # noqa: E402
    ClassLevel, ContentSource, LessonPlan, Subject, TeachingActivity,
)


def _config(**overrides):
    base = dict(
        keywords=[], core_competencies=[], references=[],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _lesson():
    lp = LessonPlan(
        id="zeli-map-lp",
        scheme_of_work_id="zeli-map-scheme",
        term_config_id="zeli-map-config",
        week_number=1,
        lesson_sequence=1,
        lesson_number=1,
        lesson_date=date(2026, 9, 11),
        class_level=ClassLevel.BASIC_9,
        subject=Subject.SCIENCE,
        class_size=35,
        duration_minutes=60,
        strand="Diversity of Matter",
        sub_strand="Materials",
        content_standard="B9.1.1.1 Standard",
        indicators=["B9.1.1.1.1 Identify binary compounds"],
        indicator_codes=["B9.1.1.1.1"],
        previous_knowledge="Previous lesson: Materials",
        keywords=["Charts and Pictures", "materials", "watch", "notice"],
        teaching_learning_resources=["hand lens where available", "containers"],
        source_tlrs=["Charts and Pictures"],
        teacher_activities=[TeachingActivity(
            phase="PHASE 1 · STARTER",
            description="Generic scaffold teacher row about the topic.",
            duration_minutes=9,
        )],
        learner_activities=[TeachingActivity(
            phase="PHASE 2 · LEARNER",
            description="Generic scaffold learner row about the topic.",
            duration_minutes=12,
        )],
    )
    return lp


def _content():
    return {
        "learning_objectives": [
            "Learners can name five binary compounds.",
            "Learners can state one use of each compound.",
        ],
        "prior_knowledge": (
            "Learners already know water, table salt and rust from everyday "
            "life and earlier science lessons."
        ),
        "key_vocabulary": ["binary", "compound", "sodium chloride"],
        "resources": {
            "source_resources": ["Charts and Pictures"],
            "suggested_alternatives": [
                "Locally made chart of compound names and uses",
                "Flashcards with compound names",
            ],
        },
        "starter": {
            "activity": "Show common substances and ask what they share.",
            "duration_minutes": 10,
            "teacher_action": "Display the substances and ask guiding questions.",
            "learner_action": "Name each substance and suggest what they share.",
        },
        "main_learning": {
            "phase1": {
                "name": "Presentation",
                "activity": "Present names and formulas of five compounds.",
                "duration_minutes": 15,
                "teacher_action": "Write names and formulas on the board.",
                "learner_action": "Copy the names and formulas into books.",
                "resources_used": ["Chalkboard"],
            },
            "phase2": {
                "name": "Discussion",
                "activity": "Groups discuss the use of each compound.",
                "duration_minutes": 15,
                "teacher_action": "Guide groups and correct misconceptions.",
                "learner_action": "Share one use for each compound.",
                "resources_used": ["Exercise books"],
            },
            "phase3": {
                "name": "Application",
                "activity": "Learners match names to uses and add one example.",
                "duration_minutes": 10,
                "teacher_action": "Circulate and check each learner's matching.",
                "learner_action": "Complete the matching task and add one example.",
                "resources_used": ["Chalkboard"],
            },
        },
        "assessment": {
            "activity": "Ask learners to name a compound and state one use.",
            "success_criteria": "Each learner names three compounds and one use.",
            "duration_minutes": 10,
        },
        "plenary": {
            "activity": "Exit slip: one compound and one use.",
            "duration_minutes": 5,
            "teacher_action": "Collect slips and correct misconceptions.",
            "learner_action": "Write one compound and one use on a slip.",
        },
        "differentiation": {
            "support": "Word bank and peer pairing.",
            "core": "Complete the matching task.",
            "extension": "Write formulas for the compounds named.",
        },
        "homework_or_extension": "List three compounds used at home.",
        "teacher_notes": "Ensure the chart is visible to every learner.",
    }


def test_zeli_whole_lesson_uses_provider_prior_knowledge():
    lp = _lesson()
    GenerationPipeline()._apply_v2_content(
        lp, _content(), _config(), whole_lesson=True)
    assert lp.previous_knowledge.startswith("Learners already know water")
    # Teacher notes are not prior knowledge and must not be substituted for it.
    assert "Ensure the chart is visible" not in lp.previous_knowledge


def test_zeli_whole_lesson_replaces_generic_teacher_and_learner_columns():
    lp = _lesson()
    GenerationPipeline()._apply_v2_content(
        lp, _content(), _config(), whole_lesson=True)
    teacher_text = " ".join(a.description for a in lp.teacher_activities)
    learner_text = " ".join(a.description for a in lp.learner_activities)
    assert "Generic scaffold teacher row" not in teacher_text
    assert "Generic scaffold learner row" not in learner_text
    assert "Write names and formulas on the board" in teacher_text
    assert "Copy the names and formulas into books" in learner_text


def test_zeli_whole_lesson_drops_irrelevant_scaffold_resources():
    lp = _lesson()
    GenerationPipeline()._apply_v2_content(
        lp, _content(), _config(), whole_lesson=True)
    resources = " | ".join(lp.teaching_learning_resources).lower()
    assert "hand lens" not in resources
    assert "containers" not in resources
    assert "flashcards with compound names" in resources
    # Source TLRs remain authoritative and are never dropped.
    assert "Charts and Pictures" in lp.teaching_learning_resources


def test_zeli_ai_objectives_are_provenance_marked_ai():
    lp = _lesson()
    GenerationPipeline()._apply_v2_content(
        lp, _content(), _config(), whole_lesson=True)
    assert lp.learning_objectives
    assert all(
        obj.source == ContentSource.AI for obj in lp.learning_objectives)
    assert lp.main_activities
    assert all(
        act.source == ContentSource.AI for act in lp.main_activities)
    assert all(
        act.source == ContentSource.AI for act in lp.teacher_activities)
    assert all(
        act.source == ContentSource.AI for act in lp.learner_activities)


def test_zeli_keywords_use_provider_and_teacher_terms_only():
    lp = _lesson()
    GenerationPipeline()._apply_v2_content(
        lp, _content(), _config(keywords=["reactant"]), whole_lesson=True)
    lowered = [k.lower() for k in lp.keywords]
    assert "reactant" in lowered
    assert "binary" in lowered
    for scaffold_junk in ("watch", "notice", "materials"):
        assert scaffold_junk not in lowered


def test_zeli_timeline_honours_provider_starter_and_plenary_minutes():
    lp = _lesson()
    lp.main_activities = [
        TeachingActivity(phase="PRESENTATION", description="Present.", duration_minutes=15),
        TeachingActivity(phase="DISCUSSION", description="Discuss.", duration_minutes=15),
        TeachingActivity(phase="APPLICATION", description="Apply.", duration_minutes=10),
    ]
    lp.starter_activity = "Show common substances."
    lp.conclusion = "Exit slip: one compound and one use."
    GenerationPipeline()._complete_zeli_timeline(lp, _content())

    rows = lp.main_activities
    assert rows[0].phase == "STARTER"
    assert rows[0].duration_minutes == 10
    assert rows[-1].phase == "PLENARY"
    assert rows[-1].duration_minutes == 5
    assert rows[0].source == ContentSource.AI
    assert rows[-1].source == ContentSource.AI
    assert sum(a.duration_minutes for a in rows) == 60


def test_zeli_context_passes_only_teacher_keywords_to_the_provider():
    lp = _lesson()
    context = zeli_lesson_context(lp, _config(keywords=["reactant"]))
    assert context["teacher_keywords"] == ["reactant"]


def test_science_prompt_requires_examples_to_match_the_indicator_category():
    from src.curriculum import Indicator
    from src.curriculum.generation_prompt import build_generation_prompt
    from src.curriculum.indicator_interpreter import interpret_indicator

    indicator = Indicator(
        code="B9.1.1.1.1",
        exact_text="B9.1.1.1.1 Identify by name binary chemical compounds",
        description="Identify by name binary chemical compounds",
        source_week=1,
        source_subject="Science",
    )
    prompt = build_generation_prompt(
        subject="Science",
        class_level="Basic 9",
        strand="Diversity of Matter",
        sub_strand="Materials",
        content_standard="B9.1.1.1 Standard",
        indicator_code="B9.1.1.1.1",
        indicator_text="Identify by name binary chemical compounds",
        interpretation=interpret_indicator(indicator, "Science"),
    )
    assert "binary compound" in prompt.lower()
    assert "exactly two elements" in prompt.lower()

"""Provider-authored class assignment and assessment-item mapping."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from src.engines.generation_pipeline import GenerationPipeline  # noqa: E402
from src.models import AssessmentItem, ContentSource  # noqa: E402
from tests.test_zeli_whole_lesson_mapping import (  # noqa: E402
    _config, _content, _lesson,
)


def test_whole_lesson_uses_provider_class_assignment_and_assessment_items():
    lp = _lesson()
    lp.class_assignment = "Complete the assignment given by the teacher."
    lp.assessment_items = [AssessmentItem(prompt="Generic check")]
    content = _content()
    content["class_assignment"] = (
        "Each learner writes the name and formula of three binary compounds "
        "and states one use of each in their exercise book.")
    content["assessment_items"] = [
        {
            "prompt": "Name the binary compound with formula H2O and state one use.",
            "expected_evidence": "Learner says water and one correct use.",
            "marking_guidance": "Tick only when both name and use are correct.",
            "misconception": "Calling a mixture a compound.",
        },
        {
            "prompt": "Name one binary compound not discussed in class.",
            "expected_evidence": "A valid two-element compound such as MgO.",
            "marking_guidance": "Accept any chemically valid binary compound.",
            "misconception": "Naming a carbonate or bicarbonate.",
        },
    ]

    GenerationPipeline()._apply_v2_content(
        lp, content, _config(), whole_lesson=True)

    assert lp.class_assignment.startswith("Each learner writes the name")
    assert "Complete the assignment given by the teacher" not in lp.class_assignment
    assert len(lp.assessment_items) == 2
    assert lp.assessment_items[0].prompt.startswith("Name the binary compound")
    assert lp.assessment_items[0].expected_evidence == (
        "Learner says water and one correct use.")
    assert all(
        item.source == ContentSource.AI for item in lp.assessment_items)


def test_absent_provider_fields_keep_existing_deterministic_content():
    lp = _lesson()
    lp.class_assignment = "Existing specific task."
    lp.assessment_items = [AssessmentItem(prompt="Existing check")]
    content = _content()
    content.pop("class_assignment", None)
    content.pop("assessment_items", None)

    GenerationPipeline()._apply_v2_content(
        lp, content, _config(), whole_lesson=True)

    assert lp.class_assignment == "Existing specific task."
    assert [i.prompt for i in lp.assessment_items] == ["Existing check"]

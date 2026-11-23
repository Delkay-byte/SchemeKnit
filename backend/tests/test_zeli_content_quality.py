"""Regression tests for Zeli lesson quality and teacher-authored voice.

These tests describe the required generation contract before the production
guard is implemented. They are intentionally strict about teacher-action
voice and pedagogical completeness while leaving learner-action prose natural.
"""
import pytest

from src.curriculum.generation_prompt import (
    LESSON_OUTPUT_SCHEMA,
    SYSTEM_PROMPT,
    build_generation_prompt,
)
from src.curriculum.indicator_interpreter import IndicatorInterpretation
from src.engines.zeli_generation import (
    ZELI_OUTPUT_ALLOWLIST,
    filter_zeli_content_to_allowlist,
)
from src.engines.zeli_quality import (
    focus_terms_from_text,
    generic_rubric_detected,
    lesson_content_fingerprint,
    normalize_zeli_teacher_voice,
    passive_teacher_direction,
    third_person_teacher_narration,
    validate_zeli_quality,
    zeli_teacher_voice,
)


SUB_STRAND = "Counting, Representation & Cardinality"


def _lesson(**overrides):
    """A complete Zeli payload using the required teacher-authored voice."""
    lesson = {
        "learning_objectives": [
            "Learners can count and represent 246 using bundles of ten and loose sticks."
        ],
        "starter": {
            "activity": "Show 24 maize kernels on the table.",
            "duration_minutes": 8,
            "teacher_action": "Write 246 on the chalkboard.",
            "learner_action": "Learners read the number aloud.",
        },
        "main_learning": {
            "phase1": {
                "name": "MODEL",
                "activity": "Demonstrate grouping 24 sticks into two tens and four ones.",
                "duration_minutes": 22,
                "teacher_action": "Demonstrate how to group the objects into tens.",
                "learner_action": "Learners group their own sticks into tens.",
            },
            "phase2": {
                "name": "PRACTISE",
                "activity": "Ask learners to represent 317 with sticks.",
                "duration_minutes": 20,
                "teacher_action": "Give learners these problems to solve independently.",
                "learner_action": "Learners build 317 in their exercise books.",
            },
        },
        "assessment": {
            "activity": "Ask each learner to represent 352 and explain the method.",
            "success_criteria": "Correct tens and units groups with a spoken explanation.",
            "duration_minutes": 7,
        },
        "plenary": {
            "activity": "Ask learners to state what each digit represents.",
            "duration_minutes": 3,
            "teacher_action": "Conclude the lesson by summarising the main points.",
            "learner_action": "Learners answer the closing question in their books.",
        },
        "worked_example": {
            "problem": "Represent 246 with bundles of ten and loose sticks.",
            "steps": [
                "Group 24 sticks into two bundles of ten and four loose sticks.",
                "Write 2 in the tens position and 4 in the units position.",
            ],
            "answer": "2 tens and 4 ones, written as 24.",
            "reasoning": "Each bundle stands for ten, so two bundles and four loose sticks make 24.",
        },
        "practice_questions": [
            {
                "question": "Represent 317 using bundles of ten and loose sticks.",
                "expected_answer": "3 tens and 17 ones, or 3 tens and 1 ten 7 ones after regrouping.",
                "reasoning": "Three bundles of ten and seventeen loose sticks total 317.",
            }
        ],
        "assessment_items": [
            {
                "prompt": "Represent 352 and explain your grouping.",
                "expected_evidence": "Learner shows three hundreds, five tens and two units.",
                "marking_guidance": "Award one mark for each correct place value and one for the explanation.",
                "misconception": "Learner treats the 5 as five hundreds.",
            }
        ],
        "differentiation": {
            "support": "Give a partially completed example and extra sticks.",
            "core": "Represent three two-digit numbers.",
            "extension": "Create and solve a partner's number.",
        },
        "resource_guidance": {
            "preparation": "Count 30 sticks into ten bundles before the lesson.",
            "use": "Each group of five learners shares one bundle set.",
            "no_cost_alternative": "Use straws, beans or bottle tops if sticks are scarce.",
        },
    }
    lesson.update(overrides)
    return lesson


def test_complete_teacher_authored_lesson_passes_quality_validation():
    assert validate_zeli_quality(_lesson(), sub_strand=SUB_STRAND) == []


@pytest.mark.parametrize(
    "text",
    [
        "The teacher goes round checking learners' work.",
        "The teacher writes the numbers on the board.",
        "The teacher asks learners to solve the problem.",
        "The facilitator is required to guide learners.",
    ],
)
def test_third_person_teacher_narration_is_detected(text):
    assert third_person_teacher_narration(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "Move around the classroom and check learners' work.",
        "Learners identify the thousands, hundreds, tens and units digits.",
        "Ask learners to work in pairs.",
        "Write 3,456 on the chalkboard.",
    ],
)
def test_direct_instructions_and_learner_actions_are_not_flagged(text):
    assert third_person_teacher_narration(text) is False


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("The teacher goes round checking learners' work.",
         "Move around the classroom and check learners' work."),
        ("The teacher writes the numbers on the board.",
         "Write the numbers on the board."),
        ("The teacher asks learners to solve the problem.",
         "Ask learners to solve the problem."),
        ("The teacher demonstrates how to use the counters.",
         "Demonstrate how to use the counters."),
        ("Write 246 on the chalkboard.", "Write 246 on the chalkboard."),
    ],
)
def test_teacher_voice_uses_direct_imperative(source, expected):
    assert zeli_teacher_voice(source) == expected


def test_third_person_narration_inside_activity_prose_fails_quality_gate():
    lesson = _lesson()
    lesson["starter"]["activity"] = (
        "Learners count maize kernels while the teacher writes the totals "
        "on the chalkboard."
    )
    assert "third_person_teacher_voice" in validate_zeli_quality(
        lesson, sub_strand=SUB_STRAND)


def test_learner_action_mentioning_the_teacher_is_not_flagged():
    text = "Learners listen to the teacher and repeat the number aloud."
    assert third_person_teacher_narration(text) is False
    assert passive_teacher_direction(text) is False


def test_passive_direction_fails_quality_gate():
    lesson = _lesson()
    lesson["main_learning"]["phase1"]["teacher_action"] = (
        "Learners are expected to be guided through the worked example."
    )
    assert "passive_teacher_direction" in validate_zeli_quality(
        lesson, sub_strand=SUB_STRAND)


def test_normalizer_only_rewrites_teacher_action_fields():
    lesson = _lesson()
    lesson["main_learning"]["phase1"]["teacher_action"] = (
        "The teacher goes round checking learners' work."
    )
    lesson["main_learning"]["phase1"]["learner_action"] = (
        "Learners check their partner's work."
    )
    normalized = normalize_zeli_teacher_voice(lesson)
    phase = normalized["main_learning"]["phase1"]
    assert phase["teacher_action"] == (
        "Move around the classroom and check learners' work.")
    assert phase["learner_action"] == "Learners check their partner's work."
    assert lesson["main_learning"]["phase1"]["teacher_action"] == (
        "The teacher goes round checking learners' work.")


def test_third_person_narration_in_teacher_actions_fails_quality_gate():
    lesson = _lesson()
    lesson["main_learning"]["phase1"]["teacher_action"] = (
        "The teacher goes round checking learners' work."
    )
    assert "third_person_teacher_voice" in validate_zeli_quality(
        lesson, sub_strand=SUB_STRAND)


def test_missing_worked_example_fails_quality_gate():
    lesson = _lesson()
    del lesson["worked_example"]
    assert "missing_worked_example" in validate_zeli_quality(
        lesson, sub_strand=SUB_STRAND)


def test_missing_practice_questions_fails_quality_gate():
    lesson = _lesson()
    del lesson["practice_questions"]
    assert "missing_practice_questions" in validate_zeli_quality(
        lesson, sub_strand=SUB_STRAND)


def test_practice_question_without_expected_answer_fails_quality_gate():
    lesson = _lesson()
    lesson["practice_questions"][0].pop("expected_answer")
    assert "missing_expected_answers" in validate_zeli_quality(
        lesson, sub_strand=SUB_STRAND)


def test_missing_marking_guidance_fails_quality_gate():
    lesson = _lesson()
    lesson["assessment_items"][0]["marking_guidance"] = ""
    assert "missing_marking_guidance" in validate_zeli_quality(
        lesson, sub_strand=SUB_STRAND)


def test_missing_phase_durations_fails_quality_gate():
    lesson = _lesson()
    del lesson["main_learning"]["phase1"]["duration_minutes"]
    assert "missing_phase_durations" in validate_zeli_quality(
        lesson, sub_strand=SUB_STRAND)


def test_phase_durations_must_match_configured_period():
    lesson = _lesson()
    assert "timing_mismatch" in validate_zeli_quality(
        lesson, sub_strand=SUB_STRAND, duration_minutes=70)
    assert "timing_mismatch" not in validate_zeli_quality(
        lesson, sub_strand=SUB_STRAND, duration_minutes=60)


def test_sub_strand_repetition_in_instructional_prose_fails_quality_gate():
    lesson = _lesson()
    repeated = (
        f"Work through one example of {SUB_STRAND}. "
        f"Ask learners to solve two problems on {SUB_STRAND}. "
        f"Check each group's work on {SUB_STRAND}."
    )
    lesson["main_learning"]["phase1"]["activity"] = repeated
    assert "sub_strand_repetition" in validate_zeli_quality(
        lesson, sub_strand=SUB_STRAND)


def test_sub_strand_twice_fails_and_once_passes_in_instructional_prose():
    lesson = _lesson()
    lesson["main_learning"]["phase1"]["activity"] = (
        f"Introduce {SUB_STRAND} with a basket of maize kernels. "
        f"Then regroup kernels using the {SUB_STRAND} method."
    )
    assert "sub_strand_repetition" in validate_zeli_quality(
        lesson, sub_strand=SUB_STRAND)
    lesson["main_learning"]["phase1"]["activity"] = (
        f"Introduce {SUB_STRAND} with a basket of maize kernels."
    )
    assert "sub_strand_repetition" not in validate_zeli_quality(
        lesson, sub_strand=SUB_STRAND)


def test_generic_activity_without_teaching_content_fails_quality_gate():
    lesson = _lesson()
    lesson["main_learning"]["phase2"]["activity"] = "Solve two problems."
    assert "generic_activity" in validate_zeli_quality(
        lesson, sub_strand=SUB_STRAND)


def test_rural_resource_guidance_is_required():
    lesson = _lesson()
    del lesson["resource_guidance"]
    assert "missing_resource_guidance" in validate_zeli_quality(
        lesson, sub_strand=SUB_STRAND)


def test_no_cost_alternative_may_be_empty_when_not_needed():
    lesson = _lesson()
    lesson["resource_guidance"]["no_cost_alternative"] = ""
    assert "missing_resource_guidance" not in validate_zeli_quality(
        lesson, sub_strand=SUB_STRAND)


def test_unapproved_or_unsuitable_resource_fails_quality_gate():
    lesson = _lesson()
    lesson["resources"] = {"source_resources": ["Projector"]}
    failures = validate_zeli_quality(
        lesson, sub_strand=SUB_STRAND,
        allowed_resources=["Maize kernels", "Sticks"])
    assert "unrelated_resource" in failures


def test_resource_outside_teacher_list_fails_quality_gate():
    lesson = _lesson()
    lesson["resources"] = {"source_resources": ["Workbook page 19"]}
    assert "unrelated_resource" in validate_zeli_quality(
        lesson, sub_strand=SUB_STRAND, allowed_resources=["Sticks"])


def test_teacher_supplied_resource_passes_quality_gate():
    lesson = _lesson()
    lesson["resources"] = {"source_resources": ["Sticks"]}
    assert "unrelated_resource" not in validate_zeli_quality(
        lesson, sub_strand=SUB_STRAND, allowed_resources=["Sticks"])


def test_generic_rubric_without_task_focus_is_detected():
    rubric = {
        "task": "The learner's work for the lesson task",
        "criteria": [{
            "criterion": "Meets the stated criteria of the task",
            "descriptors": [
                {"descriptor": "All criteria met"},
                {"descriptor": "Most criteria met"},
            ],
        }],
    }
    focus = focus_terms_from_text(
        "Represent numbers by regrouping bundles of sticks")
    assert generic_rubric_detected(rubric, focus) is True
    assert "generic_rubric" in validate_zeli_quality(
        _lesson(), sub_strand=SUB_STRAND, rubric=rubric, focus_terms=focus)
    rubric["task"] = "Regroup sticks into tens and ones"
    assert generic_rubric_detected(rubric, focus) is False


def test_identical_content_across_indicators_has_the_same_fingerprint():
    first = lesson_content_fingerprint(_lesson())
    other = _lesson()
    other["worked_example"]["problem"] = "Represent 318 with bundles of ten."
    assert first == lesson_content_fingerprint(_lesson())
    assert first != lesson_content_fingerprint(other)


def test_pipeline_flags_duplicate_content_across_different_indicators():
    from src.engines.generation_pipeline import GenerationPipeline

    changed = _lesson()
    changed["worked_example"]["problem"] = "Represent 318 with bundles of ten."
    records = [
        {"success": True, "indicator_code": "B4.1.1.1.1", "content": _lesson()},
        {"success": True, "indicator_code": "B4.1.1.1.2", "content": _lesson()},
        {"success": True, "indicator_code": "B4.1.1.1.3", "content": changed},
    ]
    assert GenerationPipeline._duplicate_indicator_content_positions(records) == {1}


def test_prompt_declares_worked_example_and_practice_contract():
    assert '"worked_example"' in LESSON_OUTPUT_SCHEMA
    assert '"practice_questions"' in LESSON_OUTPUT_SCHEMA
    assert '"resource_guidance"' in LESSON_OUTPUT_SCHEMA


def test_prompt_requires_direct_teacher_voice_and_low_cost_resources():
    assert "imperative" in SYSTEM_PROMPT.lower()
    assert "the teacher" not in SYSTEM_PROMPT.lower()
    assert "bottle tops" in SYSTEM_PROMPT.lower()
    assert "locally available" in SYSTEM_PROMPT.lower()


def test_provider_cannot_write_teacher_config_fields():
    payload = {
        "learning_objectives": ["Learners can count bundles."],
        "starter": {"activity": "Show 24 sticks."},
        "worked_example": _lesson()["worked_example"],
        "school_name": "Hacked School",
        "teacher_name": "Hacked Teacher",
        "class_size": 999,
        "lesson_duration_minutes": 5,
        "term": "Third Term",
        "template_id": "tpl-hacked",
        "generation_method": "standard",
        "indicator_keywords": {"week1:0:X": ["hacked"]},
        "indicator_wapef": {"week1:0:X": {"gods_story": "hacked"}},
        "lesson_identity": {"subject": "Hacked"},
    }
    filtered = filter_zeli_content_to_allowlist(payload)
    assert set(filtered) <= set(ZELI_OUTPUT_ALLOWLIST)
    assert "worked_example" in filtered
    for key in ("school_name", "teacher_name", "class_size",
                "lesson_duration_minutes", "term", "template_id",
                "generation_method", "indicator_keywords", "indicator_wapef",
                "lesson_identity"):
        assert key not in filtered


def test_prompt_does_not_force_sub_strand_into_every_phase():
    interpretation = IndicatorInterpretation(
        indicator_code="B4.1.1.1.1",
        indicator_text="Learners can solve two problems showing each step of the method.",
        bloom_level="apply",
        bloom_verbs=["solve"],
        activity_type="problem_solving",
        activity_keywords=["solve"],
        primary_action="solve two problems",
        expected_performance="correct solutions with each step shown",
        knowledge_focus="number and place value",
        evidence_of_achievement="correct answers with working",
        prerequisite_knowledge="counting to 100",
        misconception_risks="skipping steps",
        assessment_mode="written exercise",
        suggested_phases=["model", "practise", "apply"],
        suggested_resources=["sticks"],
        subject_context="Use concrete objects.",
    )
    prompt = build_generation_prompt(
        subject="Mathematics",
        class_level="Basic 4",
        strand="Number",
        sub_strand=SUB_STRAND,
        content_standard="B4.1.1.1",
        indicator_code="B4.1.1.1.1",
        indicator_text="Learners can solve two problems showing each step of the method.",
        interpretation=interpretation,
    )
    assert "name the indicator's action verb and key topic words" not in prompt
    assert "at most once" in prompt.lower()

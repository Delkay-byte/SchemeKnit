"""Regression tests: saved rubric matrix export and assessment language."""
from __future__ import annotations

from datetime import date

from docx import Document

from src.models import (
    AnalyticRubric,
    AssessmentItem,
    LessonPlan,
    RubricCriterion,
    Subject,
)
from src.curriculum.assessment_design import build_assessment_items
from src.engines.docx_export import (
    DOCXExportEngine,
    required_rubric_missing,
    rubric_matrix_rows,
)


def _rubric() -> AnalyticRubric:
    return AnalyticRubric(
        task="The learner's discussion notes on fourth-generation computers",
        criteria=[
            RubricCriterion(
                criterion="Key idea stated",
                points=4,
                descriptors=[
                    {"level": "4 — exceeds the standard", "descriptor": "Accurate with a fresh example", "points": "4"},
                    {"level": "3 — meets the standard", "descriptor": "Accurate in own words", "points": "3"},
                    {"level": "2 — developing", "descriptor": "Partly accurate", "points": "2"},
                    {"level": "1 — needs support", "descriptor": "Not the lesson's idea", "points": "1"},
                ],
            )
        ],
        total_points=4,
        evidence_to_award="Award only for visible evidence.",
        authority_note="SchemeKnit-generated marking guide.",
    )


def _lesson(**overrides) -> LessonPlan:
    base = dict(
        scheme_of_work_id="scheme-1", term_config_id="job-1",
        week_number=1, lesson_sequence=1, lesson_date=date(2026, 9, 11),
        lesson_number=1, school_name="Awasive MA JHS", teacher_name="T",
        subject=Subject.ICT, class_level="Basic 7", class_size=24,
        duration_minutes=60, strand="Introduction to Computing",
        sub_strand="Components of Computers and Computer Systems",
        content_standard="B7.1.1.1 Examine the parts of a computer.",
        indicators=["B7.1.1.1.1 Discuss the fourth-generation computers"],
        lesson_topic="Fourth-generation computers",
        assessment="Assess the discussion.",
        conclusion="Summarise.",
        references=["Computing Curriculum, p. 12"],
        core_competencies=["CC"],
    )
    base.update(overrides)
    return LessonPlan(**base)


def test_rubric_rows_keep_every_saved_descriptor():
    rows = rubric_matrix_rows(_rubric())
    assert rows == [[
        "Key idea stated",
        "Accurate with a fresh example",
        "Accurate in own words",
        "Partly accurate",
        "Not the lesson's idea",
    ]]


def test_docx_contains_real_rubric_matrix_table(tmp_path):
    lesson = _lesson(assessment_rubric=_rubric())
    out = tmp_path / "rubric.docx"
    DOCXExportEngine().export_official_ges([lesson], out)

    doc = Document(str(out))
    matrices = [t for t in doc.tables
                if t.rows and t.rows[0].cells[0].text.strip() == "Criterion"]
    assert matrices, "the exported DOCX has no scoring-rubric matrix table"
    table = matrices[0]
    assert [c.text for c in table.rows[0].cells] == [
        "Criterion", "4 — exceeds the standard", "3 — meets the standard",
        "2 — developing", "1 — needs support",
    ]
    assert table.rows[1].cells[0].text == "Key idea stated"
    assert "Accurate in own words" in table.rows[1].cells[2].text


def test_export_gate_names_the_lesson_missing_its_rubric():
    lesson = _lesson(assessment_items=[
        AssessmentItem(prompt="Each learner explains one reason.", dok_level=2),
    ])
    missing = required_rubric_missing([lesson])
    assert missing and "Lesson 1" in missing[0]

    lesson_with_rubric = _lesson(
        assessment_items=[
            AssessmentItem(prompt="Each learner explains one reason.", dok_level=2),
        ],
        assessment_rubric=_rubric(),
    )
    assert required_rubric_missing([lesson_with_rubric]) == []


def test_early_years_lesson_is_not_blocked_by_rubric_gate():
    lesson = _lesson(class_level="Nursery 2", assessment_items=[
        AssessmentItem(prompt="Each learner sings the song.", dok_level=1),
    ])
    assert required_rubric_missing([lesson]) == []


def test_indicator_phrase_is_not_spliced_after_a_noun_verb():
    items = build_assessment_items(
        indicator="B7.1.1.1.1 Discuss the fourth-generation computers",
        indicator_code="B7.1.1.1.1",
        focus="discuss the fourth-generation computers",
        subject="Computing",
        class_level="Basic 7",
    )
    text = " ".join(item["prompt"] for item in items)
    assert "demonstrates discuss" not in text
    assert "shows they can discuss the fourth-generation computers" in text


def test_context_follow_up_is_a_complete_sentence():
    items = build_assessment_items(
        indicator="B7.1.1.1.2 Use input devices",
        indicator_code="B7.1.1.1.2",
        focus="use input devices",
        subject="Computing",
        class_level="Basic 7",
        context_hint=("Frame the task around a real community need — a school "
                      "register, a market inventory or a clinic queue."),
    )
    follow_ups = " ".join(item["follow_up"] for item in items)
    assert "in Frame the task" not in follow_ups
    assert "What would change if this example" in follow_ups

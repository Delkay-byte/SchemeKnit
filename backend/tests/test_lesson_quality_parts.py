"""Parts F/G/H/J — lesson resource provenance, phase structure and exports.

These tests exercise the real deterministic builder, the canonical DOCX form
and the DOCX-derived PDF. Nothing is mocked at the lesson-content level.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from src.engines.allocation_engine import AllocationEngine
from src.engines.calendar_engine import CalendarEngine
from src.engines.docx_export import DOCXExportEngine
from src.engines.generation_pipeline import GenerationPipeline
from src.engines.lesson_quality_gate import evaluate, build_entry
from src.models import (
    AIMode, ClassLevel, GenerationMethod, SchemeOfWork, Subject, TemplateType,
    TermConfig, Week, WeekType,
)
from src.curriculum.lesson_rubric import phase_assessments, phase_rows


def _weeks():
    return [
        Week(
            id="w1", week_number=1, week_type=WeekType.INSTRUCTION,
            start_date=date(2026, 9, 7), end_date=date(2026, 9, 11),
            strand="Introduction to Computing", sub_strand="Generation of Computers",
            content_standards=["B6.1.1.1 : Identify parts of a computer"],
            indicators=["B6.1.1.1.1 Describe the generations of computers"],
            resources=["Computer", "Printer", "Charts"], scheme_of_work_id="s",
        ),
        Week(
            id="w2", week_number=2, week_type=WeekType.INSTRUCTION,
            start_date=date(2026, 9, 14), end_date=date(2026, 9, 18),
            strand="Introduction to Computing",
            sub_strand="Generation of Computers and Parts of a Computer",
            content_standards=[
                "B6.1.1.1 : Identify parts of a computer, technology tools"],
            indicators=[
                "B6.1.1.1.2 Identify components of a Computer System: "
                "Hardware, Software and Peopleware"],
            resources=["printer", "Computer", "USB mouse", "Exercise books"],
            scheme_of_work_id="s",
        ),
    ]


@pytest.fixture
def generated():
    scheme = SchemeOfWork(
        id="s", filename="Lesson_Plans_Basic_6_Computing.docx",
        upload_date=datetime.now(), subject=Subject.ICT,
        class_level=ClassLevel.BASIC_6, term="First Term",
        academic_year="2026/2027", weeks=_weeks(), status="uploaded",
    )
    config = TermConfig(
        scheme_of_work_id="s", term_start_date="2026-09-07",
        term_end_date="2026-09-18", lessons_per_week=2,
        lesson_duration_minutes=60, class_size=22, teaching_days=[2, 4],
        holidays=[], ai_mode=AIMode.OFF,
        generation_method=GenerationMethod.STANDARD,
        template_type=TemplateType.GES_STYLE,
        template_id="tpl-official-ges-nacca-jhs", include_special_weeks=False,
        subject=Subject.ICT, class_level=ClassLevel.BASIC_6,
        school_name="Awasive M/A JHS", teacher_name="Mabel Asamoah",
        period="2nd & 4th", references=["Computing curriculum pg.16"],
    )
    pipeline = GenerationPipeline()
    job = pipeline.generate_all(scheme, config, template_id=config.template_id)
    assert job.status.value == "completed"
    return pipeline, job, config


def test_scheme_order_is_week_1_then_week_2(generated):
    _pipeline, job, _config = generated
    assert [lp.week_number for lp in job._lesson_plans] == [1, 2]
    assert [lp.lesson_sequence for lp in job._lesson_plans] == [1, 2]
    assert job._lesson_plans[0].indicator_codes == ["B6.1.1.1.1"]


def test_tlrs_come_only_from_the_scheme(generated):
    _pipeline, job, _config = generated
    lp = job._lesson_plans[1]
    assert lp.source_tlrs == [
        "printer", "Computer", "USB mouse", "Exercise books"]
    assert lp.teaching_learning_resources == lp.source_tlrs
    forbidden = ("hand lens", "flowchart", "diagram", "unplugged",
                 "picture card", "locally available", "recording sheet")
    joined = " ".join(lp.teaching_learning_resources).lower()
    assert not any(item in joined for item in forbidden)


def test_every_source_resource_is_used_in_a_phase(generated):
    _pipeline, job, _config = generated
    for lp in job._lesson_plans:
        body = " ".join(
            [lp.introduction, lp.starter_activity, lp.assessment, lp.conclusion]
            + [a.description or "" for a in (
                list(lp.main_activities) + list(lp.learner_activities)
                + list(lp.teacher_activities))]
        ).lower()
        for resource in lp.teaching_learning_resources:
            assert resource.lower() in body, (lp.week_number, resource)


def test_teacher_added_tlr_is_used_not_just_listed(generated):
    _pipeline, job, _config = generated
    from src.routers.generation import _ensure_resources_used

    lp = job._lesson_plans[1]
    lp.other_tlrs = ["Picture cards"]
    _ensure_resources_used(lp)
    assert "Picture cards" in lp.teaching_learning_resources
    body = " ".join(
        [lp.introduction, lp.starter_activity, lp.assessment, lp.conclusion]
        + [a.description or "" for a in lp.main_activities]
    ).lower()
    assert "picture cards" in body


def test_phase_assessments_are_distinct(generated):
    _pipeline, job, _config = generated
    for lp in job._lesson_plans:
        values = phase_assessments(lp)
        assert values["phase_1"] and values["phase_2"] and values["phase_3"]
        assert len(set(values.values())) == 3


def test_phase_1_is_not_repeated_in_phase_2(generated):
    _pipeline, job, _config = generated
    for lp in job._lesson_plans:
        p1, p2, _p3 = phase_rows(lp)
        p1_text = " ".join(a.description or "" for a in p1).lower()
        p2_text = " ".join(a.description or "" for a in p2).lower()
        assert p1_text
        assert p2_text
        # The deterministic builder's Phase 2 must not start with the Phase 1
        # opening sentence verbatim.
        first = (p1[0].description or "").split(".")[0].strip().lower()
        assert first and first not in p2_text


def test_zeli_style_starter_copy_is_removed_from_main(generated):
    pipeline, job, _config = generated
    lp = job._lesson_plans[1]
    starter = (
        "Teacher displays the computer, printer and USB mouse at the front. "
        "Learners observe and say what they see.")
    lp.starter_activity = starter
    lp.main_activities[1].description = starter + " Teacher writes responses."
    lp.teacher_activities[1].description = starter
    pipeline._strip_cross_phase_repetition(lp)
    main_text = " ".join(
        a.description or "" for a in lp.main_activities
        if not any(k in (a.phase or "").upper()
                   for k in ("STARTER", "PHASE 1", "PLENARY", "PHASE 3"))
    ).lower()
    assert starter.lower() not in main_text
    # The unique remainder of the row is preserved (only the copy is removed).
    assert "teacher writes responses" in main_text


def test_zeli_style_exit_check_is_kept_only_in_the_plenary(generated):
    pipeline, job, _config = generated
    lp = job._lesson_plans[1]
    exit_line = "Exit check: each learner names one hardware example before leaving."
    lp.conclusion = exit_line
    lp.main_activities[1].description = exit_line + " Continue the next step."
    pipeline._strip_cross_phase_repetition(lp)
    main_text = " ".join(a.description or "" for a in lp.main_activities).lower()
    assert "exit check" not in main_text
    assert "exit check" in lp.conclusion.lower()


def test_multiple_selected_competencies_survive_generation(generated):
    _pipeline, job, _config = generated
    from src.routers.generation import _apply_lesson_review_draft

    lp = job._lesson_plans[1]
    _apply_lesson_review_draft(lp, {
        "2": {"core_competencies": [
            "Critical Thinking and Problem Solving (CP)",
            "Digital Literacy (DL)",
            "Communication and Collaboration (CC)",
        ]}
    })
    assert lp.core_competencies == [
        "Critical Thinking and Problem Solving (CP)",
        "Digital Literacy (DL)",
        "Communication and Collaboration (CC)",
    ]


def test_ai_resources_never_enter_the_tlr_list(generated):
    _pipeline, job, _config = generated
    pipeline, _job, config = generated
    lp = job._lesson_plans[1]
    before = list(lp.teaching_learning_resources)
    pipeline._apply_v2_content(lp, {
        "learning_objectives": ["Learners can identify hardware"],
        "resources": {"suggested_alternatives": ["hand lens", "flowchart"]},
        "main_learning": {
            "phase1": {
                "name": "PHASE 2: MAIN", "activity": "Explore hardware",
                "resources_used": ["hand lens"],
            }
        },
    }, config, whole_lesson=True)
    assert lp.teaching_learning_resources == before
    assert "hand lens" not in lp.teaching_learning_resources


def test_metadata_is_identical_for_standard_and_zeli(generated):
    pipeline, job, config = generated
    standard = job._lesson_plans[1]
    from copy import deepcopy
    zeli = deepcopy(standard)
    pipeline._apply_v2_content(zeli, {
        "learning_objectives": ["Learners can identify hardware"],
        "starter": {"activity": "Show a keyboard."},
        "main_learning": {"p": {
            "name": "PHASE 2: MAIN", "activity": "Sort the items.",
            "teacher_action": "Model sorting.", "learner_action": "Sort."}},
        "assessment": {"activity": "Check sorting.",
                       "success_criteria": "All items sorted."},
        "plenary": {"activity": "Recap."},
    }, config, whole_lesson=True)
    for field in (
        "class_size", "class_level", "subject", "school_name", "teacher_name",
        "week_number", "week_ending", "duration_minutes", "period",
        "strand", "sub_strand", "content_standard", "indicator_codes",
        "lesson_sequence",
    ):
        assert getattr(zeli, field) == getattr(standard, field), field


def test_docx_phase_table_has_assessment_only_third_column(generated, tmp_path):
    _pipeline, job, config = generated
    out = DOCXExportEngine().export_official_ges(
        job._lesson_plans, tmp_path / "basic6.docx",
        context={"school_name": config.school_name,
                 "teacher_name": config.teacher_name,
                 "period": config.period,
                 "teaching_days": ["Wednesday", "Friday"]},
    )
    import docx

    document = docx.Document(str(out))
    tables = [t for t in document.tables
              if len(t.columns) == 3
              and t.rows[0].cells[2].text.strip().upper() == "ASSESSMENT"]
    assert len(tables) == 2
    for table in tables:
        header = [c.text.strip() for c in table.rows[0].cells]
        assert header == ["PHASE / TIMELINE",
                          "LEARNER & TEACHER ACTIVITIES", "ASSESSMENT"]
        for row in table.rows[1:]:
            assessment = row.cells[2].text.lower()
            assert "computer, printer" not in assessment
            assert "usb mouse" not in assessment


def test_pdf_is_structurally_parity_with_docx(generated, tmp_path):
    _pipeline, job, config = generated
    from src.engines.pdf_export import PDFExportEngine

    docx_path = DOCXExportEngine().export_official_ges(
        job._lesson_plans, tmp_path / "basic6.docx",
        context={"school_name": config.school_name,
                 "teacher_name": config.teacher_name,
                 "period": config.period,
                 "teaching_days": ["Wednesday", "Friday"]},
    )
    engine = PDFExportEngine()
    if not engine.is_available():
        pytest.skip("no DOCX-to-PDF converter in this environment")
    pdf_path = engine._convert_docx_to_pdf(docx_path, tmp_path / "basic6.pdf")

    import pypdf

    reader = pypdf.PdfReader(str(pdf_path))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    normalised = " ".join(text.split())
    assert "PHASE / TIMELINE" in normalised
    assert "ASSESSMENT" in normalised
    assert "LEARNER & TEACHER ACTIVITIES" in normalised
    # Both lessons' assessment structures survive the conversion.
    assert "Assessment Structure" in text
    assert "Week 1" in text and "Week 2" in text
    # The three-column delivery structure is not simplified to two columns.
    delivery_pages = [p.extract_text() or "" for p in reader.pages
                      if "ASSESSMENT" in (p.extract_text() or "")]
    assert delivery_pages
    for page in delivery_pages:
        page_norm = " ".join(page.split())
        assert "PHASE / TIMELINE" in page_norm
        assert "LEARNER & TEACHER ACTIVITIES" in page_norm
    assert len(reader.pages) >= 4

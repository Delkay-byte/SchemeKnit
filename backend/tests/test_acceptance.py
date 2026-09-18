"""
SchemeKnit End-to-End Acceptance Test

Tests the complete pipeline with real scheme documents.
"""

import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.parsers.docx_parser import DOCXParser
from src.models import SchemeOfWork, TermConfig, Subject, ClassLevel, AIMode, TemplateType
from src.engines.generation_pipeline import GenerationPipeline
from src.engines.docx_export import DOCXExportEngine
from src.engines.xlsx_export import XLSXExportEngine
from datetime import date


def _run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


async def _test_science_pipeline():
    doc_path = Path(r"C:\Users\SAVIOUR\Documents\DScience\Lesson Plan\BASIC 9 SCIENCE SCHEME OF LEARNING.docx")
    parser = DOCXParser()
    scheme = await parser.parse(doc_path)

    assert scheme.subject == Subject.SCIENCE
    assert scheme.class_level == ClassLevel.BASIC_9
    assert len(scheme.weeks) == 15

    config = TermConfig(
        scheme_of_work_id=scheme.id,
        term_start_date=date(2026, 9, 11),
        term_end_date=date(2026, 12, 18),
        lessons_per_week=3,
        lesson_duration_minutes=60,
        class_size=11,
        teaching_days=[0, 2, 4],
        holidays=[],
        ai_mode=AIMode.OFF,
        template_type=TemplateType.GES_STYLE,
        include_special_weeks=False,
        subject=scheme.subject,
        class_level=scheme.class_level,
        school_name="Test School",
        teacher_name="Test Teacher",
    )

    pipeline = GenerationPipeline()
    job = pipeline.generate_all(scheme, config)
    assert job.status.value == "completed"
    assert job.total_lessons > 0
    assert len(job._lesson_plans) > 0
    assert all(lp.subject == Subject.SCIENCE for lp in job._lesson_plans)

    print(f"Science: {len(job._lesson_plans)} lesson plans generated")
    return job


async def _test_math_pipeline():
    doc_path = Path(r"C:\Users\SAVIOUR\Documents\DScience\Lesson Plan\BASIC 9 MATH SCHEME OF LEARNING.docx")
    parser = DOCXParser()
    scheme = await parser.parse(doc_path)

    assert scheme.subject == Subject.MATHEMATICS
    assert scheme.class_level == ClassLevel.BASIC_9

    config = TermConfig(
        scheme_of_work_id=scheme.id,
        term_start_date=date(2026, 9, 11),
        term_end_date=date(2026, 12, 18),
        lessons_per_week=3,
        lesson_duration_minutes=60,
        class_size=11,
        teaching_days=[0, 2, 4],
        holidays=[],
        ai_mode=AIMode.OFF,
        template_type=TemplateType.GES_STYLE,
        include_special_weeks=False,
        subject=scheme.subject,
        class_level=scheme.class_level,
    )

    pipeline = GenerationPipeline()
    job = pipeline.generate_all(scheme, config)
    assert job.status.value == "completed"
    assert len(job._lesson_plans) > 0
    assert all(lp.subject == Subject.MATHEMATICS for lp in job._lesson_plans)

    print(f"Math: {len(job._lesson_plans)} lesson plans generated")
    return job


def test_science_pipeline():
    _run_async(_test_science_pipeline())


def test_math_pipeline():
    _run_async(_test_math_pipeline())


def test_export_science():
    job = _run_async(_test_science_pipeline())
    output_dir = Path(r"C:\Users\SAVIOUR\Documents\SchemeKnit\backend\output\science_export")
    output_dir.mkdir(parents=True, exist_ok=True)

    plans = job._lesson_plans
    pipeline = GenerationPipeline()

    docx_files = pipeline.export_docx_batch(plans, output_dir=output_dir / "docx")
    assert len(docx_files) > 0
    assert all(f.exists() for f in docx_files)
    print(f"Science DOCX: {len(docx_files)} files exported")

    xlsx_file = pipeline.export_xlsx(plans, output_dir / "register.xlsx")
    assert xlsx_file.exists()
    print(f"Science XLSX: register exported")

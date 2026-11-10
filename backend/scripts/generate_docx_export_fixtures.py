"""Generate browser-DOCX regression fixtures from the server renderer.

Run from ``backend/``:
    python scripts/generate_docx_export_fixtures.py

It writes, under ``frontend/tests/fixtures/docx/``:
- ``model.json``      — the server-built render model for four paths
- ``backend.docx``    — the python-docx document for the same model
- ``backend.txt``     — its text in document order

The frontend test rebuilds the DOCX from ``model.json`` and compares the text.
Fixtures are committed so the parity check does not depend on Python.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from docx import Document  # noqa: E402
from docx.table import Table  # noqa: E402
from docx.text.paragraph import Paragraph  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402

from src.engines.docx_export import DOCXExportEngine  # noqa: E402
from src.engines.export_model import build_docx_model  # noqa: E402
from src.engines.official_ges_levels import spec_for_template_id  # noqa: E402
from src.engines.template_engine import get_template_by_id  # noqa: E402
from src.engines.wapef_template import is_wapef_template  # noqa: E402
from src.models import (  # noqa: E402
    AssessmentItem,
    AnalyticRubric,
    ClassLevel,
    LearningObjective,
    LessonPlan,
    Subject,
    TeachingActivity,
)

OUT = ROOT.parent / "frontend" / "tests" / "fixtures" / "docx"

JHS_TEMPLATE_ID = "tpl-official-ges-nacca-jhs"
WAPEF_TEMPLATE_ID = "tpl-wapef-approved-plan"
SECTION_TEMPLATE_ID = "tpl-jhs-ges"


def lesson(week: int, sequence: int) -> LessonPlan:
    return LessonPlan(
        id=f"lp-fixture-{week}-{sequence}",
        scheme_of_work_id="scheme-fixture",
        term_config_id="job-fixture",
        week_number=week,
        teaching_week=week,
        lesson_sequence=sequence,
        lesson_number=sequence,
        lesson_date=date(2026, 2, 2 + week),
        period="2nd",
        class_level=ClassLevel.BASIC_7,
        subject=Subject.SCIENCE,
        class_size=38,
        duration_minutes=60,
        school_name="Achimota Basic School",
        teacher_name="A. Mensah",
        strand="Materials and their properties",
        sub_strand="Mixtures",
        content_standard="Demonstrate understanding of mixtures and separation.",
        content_standard_code="B7.2.1",
        indicators=["B7.2.1.1 Describe mixtures", "B7.2.1.2 Separate mixtures"],
        indicator_codes=["B7.2.1.1", "B7.2.1.2"],
        lesson_topic="Separating mixtures by filtration",
        previous_knowledge="Learners know that some solids dissolve in water.",
        learning_objectives=[
            LearningObjective(description="Explain filtration using a diagram."),
            LearningObjective(description="Separate a sand-and-water mixture."),
        ],
        core_competencies=["Critical thinking", "Collaboration"],
        teaching_learning_resources=["Filter paper", "Funnel", "Beakers"],
        introduction="Show muddy water and ask how it can be made clear.",
        main_activities=[
            TeachingActivity(
                phase="Phase 2: Active Learning",
                description="Demonstrate folding filter paper and pouring the mixture.",
                duration_minutes=25,
            )
        ],
        learner_activities=[
            TeachingActivity(
                phase="Phase 2: Active Learning",
                description="Learners filter their own sample in pairs.",
                duration_minutes=15,
            )
        ],
        teacher_activities=[
            TeachingActivity(
                phase="Phase 3: Reflection",
                description="Ask learners to compare the filtrate and residue.",
            )
        ],
        assessment="Observe each pair's filtration and question their choices.",
        assessment_items=[
            AssessmentItem(
                prompt="Why does the filter paper trap sand?",
                dok_level=2,
                expected_evidence="Names particle size as the reason.",
                marking_guidance="Accept any answer naming particle size.",
                misconception="Sand dissolves in water.",
                follow_up="Re-demonstrate with a transparent mixture.",
            )
        ],
        assessment_rubric=AnalyticRubric(
            task="Filter a sand-and-water mixture safely.",
            criteria=[
                {
                    "criterion": "Correct setup",
                    "descriptors": [
                        {"points": "4", "descriptor": "Funnel and paper seated correctly."},
                        {"points": "3", "descriptor": "Minor spillage only."},
                    ],
                }
            ],
            total_points=4,
            evidence_to_award="Award for a working setup.",
            authority_note="School assessment policy.",
        ),
        conclusion="Summarise that filtration separates insoluble solids.",
        references=["GES Science Curriculum Basic 7", "Teacher resource pack"],
        keywords=["filtration", "filtrate", "residue"],
        class_assignment="Draw and label the filtration setup.",
        home_assignment="List three household examples of filtration.",
        starter_activity="Predict what happens to muddy water in a funnel.",
    )


def document_text(path: Path) -> str:
    document = Document(str(path))
    lines: list[str] = []

    def walk(parent):
        for child in parent.iterchildren():
            if child.tag == qn("w:p"):
                text = Paragraph(child, document).text.strip()
                if text:
                    lines.append(text)
            elif child.tag == qn("w:tbl"):
                table = Table(child, document)
                seen_cells = set()
                for row in table.rows:
                    for cell in row.cells:
                        # python-docx returns the SAME merged cell once per
                        # grid position. Count it once, in document order.
                        key = cell._tc
                        if key in seen_cells:
                            continue
                        seen_cells.add(key)
                        for paragraph in cell.paragraphs:
                            text = paragraph.text.strip()
                            if text:
                                lines.append(text)

    walk(document.element.body)
    return "\n".join(lines)


def custom_structure() -> dict:
    return {
        "meta": {"title_lines": ["{subject} — {class}", "TERM {term}"]},
        "layout": {"orientation": "portrait"},
        "tables": [
            {
                "rows": 3,
                "cols": 3,
                "cells": [
                    {"r": 0, "c": 0, "label": "School", "field": "school_name"},
                    {"r": 0, "c": 1, "label": "Teacher", "field": "teacher_name"},
                    {"r": 0, "c": 2, "label": "Week", "field": "week_number"},
                    {"r": 1, "c": 0, "label": "Strand", "field": "strand",
                     "colspan": 2},
                    {"r": 1, "c": 1, "covered": True},
                    {"r": 1, "c": 2, "label": "Class", "field": "class_level"},
                    {"r": 2, "c": 0, "role": "activity_content",
                     "row_phase_kind": "starter"},
                    {"r": 2, "c": 1, "role": "activity_content",
                     "row_phase_kind": "main", "colspan": 2},
                    {"r": 2, "c": 2, "covered": True},
                ],
            }
        ],
    }


def write_case(name: str, lp_list, *, template_id=None, structure=None,
               render_context=None) -> None:
    context = render_context or {"term": "Term 1", "teaching_days": ["Monday"]}
    template = (get_template_by_id(template_id) if template_id else None)
    model = build_docx_model(
        lp_list,
        template=template,
        structure=structure,
        render_context=context,
        filename=f"{name}.docx",
        job_id="job-fixture",
    )
    engine = DOCXExportEngine()
    out = OUT / f"{name}.docx"
    if structure:
        engine.export_combined_custom(lp_list, structure, out, context)
    else:
        assert template is not None
        engine.export_combined(lp_list, template, out, context=context)
    (OUT / f"{name}.model.json").write_text(
        json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / f"{name}.txt").write_text(document_text(out), encoding="utf-8")
    print(f"{name}: {len(model['documents'])} document(s), "
          f"{model['renderer']} renderer")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    lessons = [lesson(1, 1), lesson(1, 2), lesson(2, 1)]
    write_case("official_ges", lessons, template_id=JHS_TEMPLATE_ID)
    write_case("wapef", lessons, template_id=WAPEF_TEMPLATE_ID)
    write_case("sections", lessons, template_id=SECTION_TEMPLATE_ID)
    write_case("custom_structure", lessons, structure=custom_structure())


if __name__ == "__main__":
    main()

"""Render-neutral DOCX export model.

The hosting optimisation moves *document serialization* to the teacher's
browser. Curriculum rules, template resolution, school/teacher identity, phase
composition and every content decision stay here on the server.

This module turns a persisted lesson-plan set into one JSON document model:

* ``form`` — a bundled placeholder .docx plus per-lesson token text, grid-cell
  text and header lines. The browser fills the form in place, so the approved
  table topology is preserved by construction (same contract as
  ``official_ges_template`` / ``wapef_template``).
* ``blocks`` — a neutral block list (headings, paragraphs, bullets, tables).
  The browser maps each block to the ``docx`` library. Used for the built-in
  section templates and teacher-built custom structures.

No file is written here and no DOCX package is built. The response is data.
"""

from datetime import date
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from ..models import (
    ClassLevel,
    LessonPlan,
    Subject,
    Template,
    TemplateType,
)
from .docx_export import (
    _activity_block,
    _day_row_value,
    _lesson_field_value,
    default_template_for_lessons,
)
from .official_ges_levels import spec_for_template_id
from .official_ges_template import (
    grid_fill_values,
    header_lines as ges_header_lines,
    is_ges_form_template,
    placeholder_values as ges_placeholder_values,
)
from .template_engine import get_visible_sections
from .wapef_template import (
    header_lines as wapef_header_lines,
    is_wapef_template,
    wapef_placeholder_values,
)

MODEL_SCHEMA_VERSION = 1

#: Asset filename -> public URL path served by the frontend build.
TEMPLATE_ASSET_DIR = "docx-templates"


def _display(value: Any) -> str:
    """Enum/string display value, matching the existing renderers."""
    if isinstance(value, (Subject, ClassLevel)):
        return value.value
    return str(value or "")


def _runs(*parts: tuple) -> List[Dict[str, Any]]:
    return [
        {"text": str(text), "bold": bool(bold)}
        for text, bold in parts
        if text is not None
    ]


def _paragraph(runs: Optional[List[Dict[str, Any]]] = None,
               style: Optional[str] = None) -> Dict[str, Any]:
    return {"kind": "paragraph", "runs": runs or [], "style": style}


def _heading(text: str, level: int, center: bool = False) -> Dict[str, Any]:
    return {
        "kind": "heading",
        "text": text,
        "level": level,
        "align": "center" if center else "left",
    }


def _bullets(items: List[str]) -> List[Dict[str, Any]]:
    return [_paragraph(_runs((item, False)), style="List Bullet")
            for item in items or [] if str(item or "").strip()]


def _table(rows: int, cols: int,
           cells: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "kind": "table",
        "style": "Table Grid",
        "rows": rows,
        "cols": cols,
        "cells": cells,
    }


# ── Built-in section templates ────────────────────────────────────────────────

def _header_block(lp: LessonPlan) -> List[Dict[str, Any]]:
    subject_val = _display(lp.subject)
    class_val = _display(lp.class_level)
    info_data = [
        ("School", lp.school_name or "________________"),
        ("Teacher", lp.teacher_name or "________________"),
        ("Subject", subject_val),
        ("Class", (f"{class_val}  |  Size: {lp.class_size}"
                   if lp.class_size else class_val)),
        ("Date", lp.lesson_date.strftime("%d %B %Y") if lp.lesson_date else ""),
        ("Duration", f"{lp.duration_minutes} minutes"),
    ]
    cells = []
    for row, (label, value) in enumerate(info_data):
        cells.append({"r": row, "c": 0, "text": label, "bold": True})
        cells.append({"r": row, "c": 1, "text": str(value), "bold": False})
    return [_heading("LESSON PLAN", 1, center=True), _table(6, 2, cells)]


def _strand_block(lp: LessonPlan) -> List[Dict[str, Any]]:
    strand = lp.strand or ""
    sub = lp.sub_strand or ""
    if not (strand or sub):
        return [_heading("Strand / Sub-Strand", 2)]
    blocks: List[Dict[str, Any]] = [_heading("Strand / Sub-Strand", 2)]
    if strand:
        blocks.append(_paragraph(_runs((f"Strand: {strand}", True))))
    if sub:
        blocks.append(_paragraph(_runs((f"Sub-Strand: {sub}", False))))
    return blocks


def _content_standard_block(lp: LessonPlan) -> List[Dict[str, Any]]:
    if not lp.content_standard:
        return [_heading("Content Standard", 2)]
    return [
        _heading("Content Standard", 2),
        _paragraph(_runs((f"{lp.content_standard_code} "
                          if lp.content_standard_code else None, True),
                         (lp.content_standard, False))),
    ]


def _indicators_block(lp: LessonPlan) -> List[Dict[str, Any]]:
    items = list(lp.indicators or []) or list(lp.indicator_codes or [])
    return [_heading("Indicators", 2), *_bullets(items)]


def _objectives_block(lp: LessonPlan) -> List[Dict[str, Any]]:
    objectives = [getattr(o, "description", str(o))
                  for o in (lp.learning_objectives or [])]
    return [_heading("Learning Objectives", 2), *_bullets(objectives)]


def _resources_block(lp: LessonPlan) -> List[Dict[str, Any]]:
    return [_heading("Teaching & Learning Resources", 2),
            *_bullets(list(lp.teaching_learning_resources or []))]


def _introduction_block(lp: LessonPlan) -> List[Dict[str, Any]]:
    blocks = [_heading("Introduction / Starter", 2)]
    if lp.introduction:
        blocks.append(_paragraph(_runs((lp.introduction, False))))
    return blocks


def _main_activities_block(lp: LessonPlan) -> List[Dict[str, Any]]:
    blocks = [_heading("Main Teaching Activities", 2)]
    for act in lp.main_activities or []:
        text = getattr(act, "description", str(act))
        duration = getattr(act, "duration_minutes", None)
        blocks.append(_paragraph(_runs(
            (f"{act.phase}: " if getattr(act, "phase", None) else None, True),
            (text, False),
            (f" ({duration} min)" if duration else None, False),
        )))
    return blocks


def _learner_activities_block(lp: LessonPlan) -> List[Dict[str, Any]]:
    blocks = [_heading("Learner Activities", 2)]
    for act in lp.learner_activities or []:
        text = getattr(act, "description", str(act))
        duration = getattr(act, "duration_minutes", None)
        blocks.append(_paragraph(_runs(
            (text, False),
            (f" ({duration} min)" if duration else None, False),
        )))
    return blocks


def _teacher_activities_block(lp: LessonPlan) -> List[Dict[str, Any]]:
    blocks = [_heading("Teacher Activities", 2)]
    for act in lp.teacher_activities or []:
        blocks.append(_paragraph(_runs(
            (getattr(act, "description", str(act)), False))))
    return blocks


_RUBRIC_LEVEL_NAMES = (
    "4 — exceeds the standard",
    "3 — meets the standard",
    "2 — developing",
    "1 — needs support",
)


def _assessment_blocks(lp: LessonPlan) -> List[Dict[str, Any]]:
    blocks = [_heading("Assessment", 2)]
    if lp.assessment:
        blocks.append(_paragraph(_runs((lp.assessment, False))))
    items = [i for i in (lp.assessment_items or [])
             if (getattr(i, "prompt", "") or "").strip()]
    if items:
        blocks.append(_heading("Assessment Questions / Checks (with marking)", 3))
        for item in items:
            blocks.append(_paragraph(_runs(
                (f"{item.prompt} (DoK {item.dok_level})", False)),
                style="List Bullet"))
            for prefix, value in (
                ("Expected evidence: ", getattr(item, "expected_evidence", "")),
                ("Marking: ", getattr(item, "marking_guidance", "")),
                ("Watch for: ", getattr(item, "misconception", "")),
                ("If not reached: ", getattr(item, "follow_up", "")),
            ):
                if value:
                    blocks.append(_paragraph(_runs((prefix + value, False))))
    rubric = lp.assessment_rubric
    if rubric is not None and rubric.criteria:
        blocks.append(_heading("Marking Rubric for the Learner Task", 3))
        if rubric.task:
            blocks.append(_paragraph(_runs((rubric.task, False))))
        for criterion in rubric.criteria:
            blocks.append(_paragraph(_runs(
                (f"Criterion: {criterion.criterion}", False))))
            for descriptor in criterion.descriptors:
                points = (descriptor.get("points") or "").strip()
                label = dict(zip(("4", "3", "2", "1"),
                                 _RUBRIC_LEVEL_NAMES)).get(
                                     points, f"{points} points")
                blocks.append(_paragraph(_runs(
                    (f"  {label}: {descriptor.get('descriptor', '')} "
                     f"({points} pt)", False))))
        blocks.append(_paragraph(_runs(
            (f"Total marks: {rubric.total_points}", False))))
        if rubric.evidence_to_award:
            blocks.append(_paragraph(_runs((rubric.evidence_to_award, False))))
        if rubric.authority_note:
            blocks.append(_paragraph(_runs((rubric.authority_note, False))))
    return blocks


def _conclusion_block(lp: LessonPlan) -> List[Dict[str, Any]]:
    blocks = [_heading("Conclusion / Reflection", 2)]
    if lp.conclusion:
        blocks.append(_paragraph(_runs((lp.conclusion, False))))
    return blocks


def _previous_knowledge_block(lp: LessonPlan) -> List[Dict[str, Any]]:
    if not lp.previous_knowledge:
        return []
    return [_heading("Previous Knowledge", 2),
            _paragraph(_runs((lp.previous_knowledge, False)))]


def _core_competencies_block(lp: LessonPlan) -> List[Dict[str, Any]]:
    if not lp.core_competencies:
        return []
    return [_heading("Core Competencies", 2),
            *_bullets(list(lp.core_competencies or []))]


def _references_block(lp: LessonPlan) -> List[Dict[str, Any]]:
    if not lp.references:
        return []
    return [_heading("References", 2),
            *_bullets(list(lp.references or []))]


_SECTION_BUILDERS = {
    "header": _header_block,
    "strand_info": _strand_block,
    "content_standard": _content_standard_block,
    "indicators": _indicators_block,
    "objectives": _objectives_block,
    "resources": _resources_block,
    "introduction": _introduction_block,
    "main_activities": _main_activities_block,
    "learner_activities": _learner_activities_block,
    "teacher_activities": _teacher_activities_block,
    "assessment": _assessment_blocks,
    "conclusion": _conclusion_block,
    "previous_knowledge": _previous_knowledge_block,
    "core_competencies": _core_competencies_block,
    "references": _references_block,
}


def sections_blocks(lp: LessonPlan, template: Template) -> List[Dict[str, Any]]:
    """Neutral blocks for one lesson in a built-in section template."""
    blocks: List[Dict[str, Any]] = []
    for section in get_visible_sections(template):
        builder = _SECTION_BUILDERS.get(section.name)
        if builder:
            blocks.extend(builder(lp))
    blocks.append({"kind": "pageBreak"})
    return blocks


# ── Custom (teacher-built) structures ─────────────────────────────────────────

def _custom_title_lines(lp: LessonPlan, structure: dict,
                        render_context: dict, first_lesson: bool) -> List[str]:
    meta = (structure or {}).get("meta") or {}
    school = _lesson_field_value(lp, "school_name")
    teacher = _lesson_field_value(lp, "teacher_name")
    week_no = _lesson_field_value(lp, "week_number")
    if school or teacher:
        lines: List[str] = []
        if first_lesson:
            if school:
                lines.append(school)
            if teacher:
                lines.append(teacher)
        if week_no:
            lines.append(f"WEEK {week_no}")
        return lines

    raw_lines = meta.get("title_lines") or ([meta.get("title")]
                                            if meta.get("title") else [])
    if not raw_lines:
        return []
    context = render_context or {}

    def _field(name: str, default: str = "") -> str:
        value = _lesson_field_value(lp, name)
        return value if value else default

    term = str(context.get("term") or _field("term")
               or _field("academic_year") or "").upper()
    mapping = {
        "term": term,
        "week": str(_field("week_number") or ""),
        "subject": str(_field("subject") or ""),
        "class": str(_field("class_level") or ""),
    }
    resolved: List[str] = []
    for line in raw_lines:
        try:
            text = str(line).format(**mapping)
        except Exception:
            text = str(line)
        if text.strip():
            resolved.append(text.strip())
    return resolved


def _custom_table(lp: LessonPlan, table: dict, render_context: dict) -> Optional[dict]:
    rows = int(table.get("rows", 0))
    cols = int(table.get("cols", 0))
    if rows <= 0 or cols <= 0:
        return None

    cells: List[Dict[str, Any]] = []
    covered = {(int(c.get("r", 0)), int(c.get("c", 0)))
               for c in table.get("cells", []) if c.get("covered")}
    for cell in table.get("cells", []):
        if cell.get("covered"):
            continue
        r, c = int(cell.get("r", 0)), int(cell.get("c", 0))
        if r >= rows or c >= cols:
            continue
        label = cell.get("label")
        field = cell.get("field")
        role = cell.get("role")
        bold = False
        text = ""
        runs: Optional[List[Dict[str, Any]]] = None
        if cell.get("structural_header"):
            text = cell.get("text", "")
            bold = bool(cell.get("bold", True))
        elif cell.get("is_phase_marker"):
            text = cell.get("text", "")
            bold = True
        elif role == "activity_content":
            text = _activity_block(lp, cell.get("row_phase_kind", "unknown"))
        elif role == "resource_content":
            text = _lesson_field_value(lp, "teaching_learning_resources")
        elif label and field:
            day_val = _day_row_value(label, field, lp, render_context or {})
            value = day_val if day_val is not None else _lesson_field_value(
                lp, field)
            # Label bold, value normal. The browser applies the run split.
            runs = [{"text": f"{label}: ", "bold": True},
                    {"text": value, "bold": False}]
        elif label:
            text = f"{label}:"
            bold = True
        # Unlabelled sample prose stays blank: sample content is never copied.

        colspan = int(cell.get("colspan", 1) or 1)
        if colspan > 1 and c + colspan - 1 >= cols:
            colspan = 1
        rowspan = 1
        if cell.get("v_merge_restart"):
            end_r = r
            while (end_r + 1, c) in covered and end_r + 1 < rows:
                end_r += 1
            rowspan = end_r - r + 1

        cells.append({
            "r": r, "c": c,
            "runs": runs or [{"text": text, "bold": bold}],
            "colspan": colspan,
            "rowspan": rowspan,
        })
    return {
        "kind": "customTable",
        "rows": rows,
        "cols": cols,
        "cells": cells,
    }


def structure_blocks(lp: LessonPlan, structure: dict,
                     render_context: Optional[dict] = None,
                     first_lesson: bool = True) -> List[Dict[str, Any]]:
    """Neutral blocks for one lesson rendered through a saved structure."""
    context = render_context or {}
    tables = (structure or {}).get("tables", [])
    if not tables:
        blocks = [_heading("LESSON PLAN", 1)]
        for field in ["school_name", "teacher_name", "subject", "class_level",
                      "lesson_date", "strand", "content_standard", "indicators",
                      "introduction", "assessment", "conclusion"]:
            value = _lesson_field_value(lp, field)
            if value:
                blocks.append(_heading(field.replace("_", " ").title(), 2))
                blocks.append(_paragraph(_runs((value, False))))
        blocks.append({"kind": "pageBreak"})
        return blocks

    blocks: List[Dict[str, Any]] = []
    for line in _custom_title_lines(lp, structure, context, first_lesson):
        blocks.append(_heading(line, 1, center=True))
    for table in tables:
        built = _custom_table(lp, table, context)
        if built:
            blocks.append(built)
            blocks.append(_paragraph())
    blocks.append({"kind": "pageBreak"})
    return blocks


# ── Bundled placeholder forms ────────────────────────────────────────────────

def _assessment_appendix(lp: LessonPlan) -> List[Dict[str, Any]]:
    """Additive assessment structure appended after bundled forms.

    Mirrors ``docx_export._append_assessment_structure``. The bundled forms'
    fixed cells print only composed assessment prose; assignments, DoK prompts
    and the rubric are appended so no substantive content is lost.
    """
    items = [i for i in (getattr(lp, "assessment_items", None) or [])
             if (getattr(i, "prompt", "") or "").strip()]
    rubric = getattr(lp, "assessment_rubric", None)
    class_task = (getattr(lp, "class_assignment", "") or "").strip()
    home_task = ((getattr(lp, "home_assignment", "") or "")
                 or (getattr(lp, "homework", "") or "")).strip()
    if not items and not (rubric is not None and rubric.criteria) \
            and not class_task and not home_task:
        return []

    blocks: List[Dict[str, Any]] = []

    def heading(text: str, page_break_before: bool = False) -> None:
        blocks.append({
            "text": text,
            "bold": True,
            "page_break_before": page_break_before,
        })

    def paragraph(text: str) -> None:
        blocks.append({"text": text, "bold": False, "page_break_before": False})

    heading(f"Assessment Structure — Week {lp.week_number} "
            f"(Lesson {lp.lesson_sequence})", page_break_before=True)
    if class_task or home_task:
        heading("Assignments")
        if class_task:
            paragraph(f"Class assignment: {class_task}")
        if home_task and home_task != class_task:
            paragraph(f"Home assignment: {home_task}")
    if items:
        heading("Assessment Questions / Checks (with marking)")
        for item in items:
            paragraph(f"• {item.prompt} (DoK {item.dok_level})")
            for prefix, value in (
                ("Expected evidence: ", item.expected_evidence),
                ("Marking: ", item.marking_guidance),
                ("Watch for: ", getattr(item, "misconception", "")),
                ("If not reached: ", getattr(item, "follow_up", "")),
            ):
                if value:
                    paragraph(prefix + value)
    if rubric is not None and rubric.criteria:
        heading("Marking Rubric for the Learner Task")
        if rubric.task:
            paragraph(rubric.task)
        for criterion in rubric.criteria:
            paragraph(f"Criterion: {criterion.criterion}")
            for descriptor in criterion.descriptors:
                points = (descriptor.get("points") or "").strip()
                label = dict(zip(("4", "3", "2", "1"),
                                 _RUBRIC_LEVEL_NAMES)).get(
                                     points, f"{points} points")
                paragraph(f"  {label}: {descriptor.get('descriptor', '')} "
                          f"({points} pt)")
        paragraph(f"Total marks: {rubric.total_points}")
        if rubric.evidence_to_award:
            paragraph(rubric.evidence_to_award)
        if rubric.authority_note:
            paragraph(rubric.authority_note)
    return blocks


def _lesson_filename(lp: LessonPlan) -> str:
    """Deterministic per-lesson ZIP member name (same pattern as the server)."""
    subject = _display(lp.subject).replace(" ", "_").upper()
    cls = _display(lp.class_level).replace(" ", "")
    date_str = lp.lesson_date.strftime("%Y-%m-%d") if lp.lesson_date else "nodate"
    raw = (f"{subject}_{cls}_W{int(lp.week_number or 0):02d}_"
           f"L{int(lp.lesson_sequence or 0):02d}_{date_str}")
    safe = re.sub(r'[<>:"/\\|?*]', '_', raw)
    return safe if safe.endswith(".docx") else f"{safe}.docx"


def _document_header(lp: LessonPlan, index: int) -> Dict[str, Any]:
    return {
        "lesson_id": getattr(lp, "id", None),
        "week_number": getattr(lp, "week_number", None),
        "lesson_sequence": getattr(lp, "lesson_sequence", None),
        "filename": _lesson_filename(lp),
        "first": index == 0,
    }


def _form_model(lp: LessonPlan, template: Template, render_context: dict,
                context: dict) -> Optional[Dict[str, Any]]:
    spec = spec_for_template_id(template.id)
    if spec is not None:
        first = context["first"]
        return {
            "kind": "official_ges",
            "asset": f"{TEMPLATE_ASSET_DIR}/{spec.filename}",
            "tokens": ges_placeholder_values(spec, lp, render_context),
            "grid_fills": grid_fill_values(spec, lp, render_context),
            "header_lines": ges_header_lines(lp, render_context, first=first),
            "standalone_header_lines": ges_header_lines(
                lp, render_context, first=True),
            "first": first,
            "strip_guidance": True,
            "title_pattern": (r"(?:OFFICIAL\s+)?GES\s*/\s*NaCCA\s+.*?"
                              r"LESSON\s+PLAN\s+TEMPLATE"),
        }
    if is_wapef_template(template):
        return {
            "kind": "wapef",
            "asset": f"{TEMPLATE_ASSET_DIR}/wapef_approved_plan_template.docx",
            "tokens": wapef_placeholder_values(lp, render_context),
            "grid_fills": [],
            "header_lines": wapef_header_lines(lp, render_context),
            "standalone_header_lines": wapef_header_lines(lp, render_context),
            "first": context["first"],
            "strip_guidance": False,
            "title_pattern": None,
        }
    return None


def build_docx_model(
    lesson_plans: List[LessonPlan],
    *,
    template: Optional[Template] = None,
    template_type: TemplateType = TemplateType.GES_STYLE,
    structure: Optional[dict] = None,
    render_context: Optional[dict] = None,
    filename: str = "lesson_plans.docx",
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the browser-serializable DOCX model for a persisted lesson set."""
    lessons = list(lesson_plans or [])
    context = render_context or {}
    resolved_template = template or default_template_for_lessons(
        lessons, template_type)

    model: Dict[str, Any] = {
        "schema_version": MODEL_SCHEMA_VERSION,
        "job_id": job_id,
        "filename": filename,
        "lesson_count": len(lessons),
        "template": {
            "id": getattr(resolved_template, "id", None),
            "name": getattr(resolved_template, "name", None),
        },
        "render_context": context,
    }

    if structure and structure.get("tables"):
        model["renderer"] = "blocks"
        model["structure"] = structure
        model["documents"] = [
            {
                **_document_header(lp, index),
                "blocks": structure_blocks(
                    lp, structure, context, first_lesson=(index == 0)),
            }
            for index, lp in enumerate(lessons)
        ]
        return model

    form_documents = []
    for index, lp in enumerate(lessons):
        form = _form_model(lp, resolved_template, context, {"first": index == 0})
        if form is None:
            form_documents = []
            break
        form_documents.append({
            **_document_header(lp, index),
            "form": form,
        })

    if form_documents:
        for document, lp in zip(form_documents, lessons):
            document["appendix"] = _assessment_appendix(lp)
        model["renderer"] = "form"
        model["documents"] = form_documents
        # Combined export appends every appendix after all forms (the same
        # order the python-docx renderer produces).
        model["appendices"] = [document["appendix"] for document in form_documents]
        return model

    model["renderer"] = "blocks"
    model["documents"] = [
        {
            **_document_header(lp, index),
            "blocks": sections_blocks(lp, resolved_template),
        }
        for index, lp in enumerate(lessons)
    ]
    return model

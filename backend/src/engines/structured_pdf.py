"""
SchemeKnit structured, template-aware PDF renderer (pure ReportLab).

Why this exists
---------------
The historical PDF path rendered a combined DOCX and converted it with Word or
LibreOffice. On hosts with neither converter the old fallback re-extracted TEXT
from the DOCX with PyMuPDF and wrapped those paragraphs in a PDF: every table
was flattened into lines of prose — a text dump, not a lesson plan. This module
is the always-available replacement: a real ReportLab document built from the
same LessonPlan models the DOCX path uses, with real bordered tables.

Template awareness
------------------
The section set, the section labels, their ORDER and their field labels come
from the same template identity the DOCX path dispatches on
(``is_wapef_template`` / ``is_ges_form_template`` / ``get_visible_sections``):

* Approved WAPEF Plan -> the WAPEF sections (Lesson Metadata, Curriculum
  Alignment, WAPEF Special Fields, Lesson Delivery) and each delivery row
  resolves through ``wapef_template._resolve`` (so the shared resource list
  lands in the MAIN row only, exactly as the form's own contract says).
* An official GES/NaCCA form -> that level's GES sections, resolved through
  ``official_ges_template._resolve`` (bulleted phases, code + standard text).
* Everything else -> the standard section renderer labels from the template's
  own visible sections, each activity list in its own bordered grid.

Rules honoured here (same contract as the DOCX renderers):
* only stored, non-empty fields are printed — nothing is invented;
* WAPEF selections and Remarks are printed verbatim (Through lines in the
  approved order); no value is ever repeated twice on one lesson page;
* administrative fields the template itself does not declare (school, teacher,
  week, topic …) are appended to the template's own header table rather than
  invented as extra sections;
* one lesson per page, PageBreak between lessons;
* the output always carries the %PDF signature.
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from ..models import LessonPlan, Template, TemplateType
from .docx_export import _lesson_field_value, default_template_for_lessons
from .official_ges_levels import spec_for_template_id
from .official_ges_template import (
    _resolve as _resolve_ges_field,
    is_ges_form_template,
    sections_for as ges_sections_for,
)
from .template_engine import get_visible_sections
from .wapef_template import _resolve as _resolve_wapef_token, is_wapef_template

#: Every valid PDF begins with this signature (ISO 32000-1 §7.5.2).
_PDF_MAGIC = b"%PDF-"

MARGIN_MM = 14
_PAGE_WIDTH, _PAGE_HEIGHT = A4
_CONTENT_WIDTH = _PAGE_WIDTH - 2 * MARGIN_MM * mm

_TITLE_TEXT = "LESSON PLAN"

#: Administrative fields every lesson can carry. Those the template does not
#: declare itself are appended to its header table (never invented elsewhere).
HEADER_FIELDS: Tuple[Tuple[str, str], ...] = (
    ("School", "school_name"),
    ("Teacher", "teacher_name"),
    ("Class Level", "class_level"),
    ("Subject", "subject"),
    ("Week Number", "week_number"),
    ("Teaching Week", "teaching_week"),
    ("Lesson Date", "lesson_date"),
    ("Week Ending", "week_ending"),
    ("Period", "period"),
    ("Duration (minutes)", "duration_minutes"),
    ("Lesson Topic", "lesson_topic"),
)

#: Sections that own the administrative block.
HEADER_SECTION_NAMES = frozenset({"header", "wapef_metadata"})

#: Sections whose body is one bordered delivery table.
DELIVERY_SECTION_NAMES = frozenset(
    {"main_activities", "delivery_grid", "wapef_delivery"})

#: Delivery carried by a single section (GES and WAPEF): each row is one of
#: the form's own labelled cells.
MERGED_DELIVERY_NAMES = frozenset({"delivery_grid", "wapef_delivery"})

#: Fields whose text a merged delivery row composes from other stored fields
#: (mirrors how the DOCX resolvers build those cells).
_COMPOSED_FIELDS: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "ges": {
        "introduction": ("starter_activity",),
        "main_activities": ("teacher_activities", "learner_activities"),
        "conclusion": ("reflection", "homework"),
    },
    "wapef": {
        "introduction": ("starter_activity",),
        "main_activities": ("learner_activities",),
    },
}

#: Enum values meaning "the source did not say" — never printed as content.
_UNKNOWN_VALUES = frozenset({"unknown"})

#: Grid columns for one standard-template activity section.
_ACTIVITY_HEADER = ("Phase", "Duration (min)", "Activity")
_ACTIVITY_WIDTHS = (0.16, 0.16, 0.68)

_REFERENCE_HEADER = ("Type", "Title", "Author / Publisher", "Page")
_REFERENCE_WIDTHS = (0.17, 0.33, 0.35, 0.15)

#: WAPEF template field -> WAPEF token, for fields whose canonical value comes
#: from ``wapef_template._resolve`` rather than a plain field read.
_WAPEF_TOKEN_BY_FIELD = {
    "wapef_week": "WEEK",
    "week_ending": "WEEK_ENDING",
    "strand": "STRAND",
    "sub_strand": "SUB_STRAND",
    "content_standard": "CONTENT_STANDARD",
    "indicators": "LEARNING_INDICATOR",
    "learning_objectives": "PERFORMANCE_INDICATOR",
    "core_competencies": "CORE_COMPETENCIES",
    "keywords": "KEY_WORDS",
    "introduction": "PHASE_1_STARTER",
    "main_activities": "PHASE_2_MAIN",
    "conclusion": "PHASE_3_PLENARY",
    "assessment": "EVALUATION",
    "remarks": "REMARKS",
    "wapef_through_lines": "THROUGH_LINE",
    "wapef_gods_story": "GODS_STORY",
    "wapef_deep_hope": "DEEP_HOPE",
    "wapef_storyline": "STORYLINE",
}

#: "Phase 2 Resources" -> 2, for the three WAPEF resource rows.
_PHASE_FROM_LABEL = re.compile(r"phase\s*([123])", re.I)

_ASSIGNMENTS = (
    ("Class Assignment", "class_assignment"),
    ("Home Assignment", "home_assignment"),
    ("Homework", "homework"),
)

_TITLE_STYLE = ParagraphStyle(
    "sk_title", fontName="Helvetica-Bold", fontSize=14, leading=17,
    alignment=1, textColor=HexColor("#1F3B63"), spaceAfter=8,
)
_SECTION_STYLE = ParagraphStyle(
    "sk_section", fontName="Helvetica-Bold", fontSize=10.5, leading=13,
    textColor=HexColor("#1F3B63"), spaceBefore=9, spaceAfter=3,
    keepWithNext=1,
)
_CELL_STYLE = ParagraphStyle(
    "sk_cell", fontName="Helvetica", fontSize=8.5, leading=11,
)
_CELL_LABEL_STYLE = ParagraphStyle(
    "sk_cell_label", fontName="Helvetica-Bold", fontSize=8.5, leading=11,
)
_CELL_HEAD_STYLE = ParagraphStyle(
    "sk_cell_head", fontName="Helvetica-Bold", fontSize=8.5, leading=11,
    textColor=colors.white,
)


class PDFRenderError(RuntimeError):
    """The structured renderer could not produce a valid PDF."""


# ── value resolution ─────────────────────────────────────────────────────────

def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(getattr(value, "value", value)).strip()


def _is_blank(value: str) -> bool:
    return not str(value or "").strip()


def _join_lines(parts: Sequence[str]) -> str:
    return "\n".join(p for p in parts if p)


def _family_of(template) -> str:
    if is_wapef_template(template):
        return "wapef"
    if is_ges_form_template(template) and \
            spec_for_template_id(getattr(template, "id", None)) is not None:
        return "ges"
    return "standard"


def _wapef_value(field: str, label: str, lp, ctx: Dict[str, Any]) -> str:
    """One WAPEF cell, resolved through the template's own token contract."""
    if field == "teaching_learning_resources":
        match = _PHASE_FROM_LABEL.search(label or "")
        token = f"PHASE_{match.group(1)}_RESOURCES" if match \
            else "PHASE_2_RESOURCES"
    else:
        token = _WAPEF_TOKEN_BY_FIELD.get(field)
    if not token:
        return ""
    return _resolve_wapef_token(token, lp, ctx).strip()


def _value_for(family: str, field: str, lp, ctx: Dict[str, Any],
               label: str = "", authoritative: bool = False) -> str:
    """Canonical text for one lesson field under the active template family.

    ``authoritative`` marks a field the template itself declares: its resolver
    owns the value (the WAPEF resource rows, for instance, must stay blank in
    phases 1 and 3 instead of falling back to the shared list).
    """
    value = ""
    if family == "ges":
        value = _resolve_ges_field(field, lp, ctx)
    elif family == "wapef":
        value = _wapef_value(field, label, lp, ctx)
    if _is_blank(value) and not (authoritative and family in ("ges", "wapef")):
        value = _lesson_field_value(lp, field)
    if field in ("subject", "class_level") and \
            value.strip().lower() in _UNKNOWN_VALUES:
        return ""
    return value.strip()


def _template_sections(template) -> List[Dict[str, Any]]:
    return [
        {"name": section.name, "label": section.label,
         "fields": [{"label": field.label, "field": field.name}
                    for field in section.fields]}
        for section in get_visible_sections(template)
    ]


def _ges_sections(spec) -> List[Dict[str, Any]]:
    return [
        {"name": key, "label": label,
         "fields": [{"label": field.label, "field": field.field}
                    for field in fields]}
        for key, label, fields in ges_sections_for(spec)
    ]


def _plan_for(template) -> Tuple[str, List[Dict[str, Any]]]:
    """(family, sections) for the template the export resolved."""
    if template is None:
        template = default_template_for_lessons([], TemplateType.GES_STYLE)
    if is_wapef_template(template):
        return "wapef", _template_sections(template)
    if is_ges_form_template(template):
        spec = spec_for_template_id(getattr(template, "id", None))
        if spec is not None:
            return "ges", _ges_sections(spec)
    return "standard", _template_sections(template)


def _declared_fields(sections: Sequence[Dict[str, Any]]) -> Set[str]:
    declared = {f["field"] for s in sections for f in s.get("fields", [])
                if f.get("field")}
    if "wapef_week" in declared:
        declared.add("week_number")
    return declared


# ── table builders ───────────────────────────────────────────────────────────

def _para(text: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(str(text)).replace("\n", "<br/>"), style)


def _grid_style(label_column: bool, header_row: bool) -> TableStyle:
    style = TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#7A8899")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ])
    if header_row:
        style.add("BACKGROUND", (0, 0), (-1, 0), HexColor("#1F3B63"))
    if label_column:
        style.add("BACKGROUND", (0, 0), (0, -1), HexColor("#EDF1F6"))
    return style


def _kv_table(rows: Sequence[Tuple[str, str]]) -> Table:
    data = [[_para(label, _CELL_LABEL_STYLE), _para(value, _CELL_STYLE)]
            for label, value in rows]
    table = Table(data,
                  colWidths=[_CONTENT_WIDTH * 0.32, _CONTENT_WIDTH * 0.68],
                  hAlign="LEFT")
    table.setStyle(_grid_style(label_column=True, header_row=False))
    return table


def _activity_table(rows: Sequence[Tuple[str, str, str]]) -> Table:
    data = [[_para(head, _CELL_HEAD_STYLE) for head in _ACTIVITY_HEADER]]
    data.extend([[_para(cell, _CELL_STYLE) for cell in row] for row in rows])
    table = Table(data,
                  colWidths=[_CONTENT_WIDTH * w for w in _ACTIVITY_WIDTHS],
                  repeatRows=1, hAlign="LEFT")
    table.setStyle(_grid_style(label_column=False, header_row=True))
    return table


def _reference_table(entries: Sequence[Any]) -> Table:
    data = [[_para(head, _CELL_HEAD_STYLE) for head in _REFERENCE_HEADER]]
    for entry in entries:
        if isinstance(entry, dict):
            def get(name, default="", entry=entry):
                return entry.get(name) or default
        else:
            def get(name, default="", entry=entry):
                return getattr(entry, name, None) or default
        row = [get("type", ""), get("title", ""),
               get("author_publisher", ""), get("page", "")]
        if not any(str(cell).strip() for cell in row):
            continue
        data.append([_para(cell, _CELL_STYLE) for cell in row])
    table = Table(data,
                  colWidths=[_CONTENT_WIDTH * w for w in _REFERENCE_WIDTHS],
                  repeatRows=1, hAlign="LEFT")
    table.setStyle(_grid_style(label_column=False, header_row=True))
    return table


# ── lesson content ───────────────────────────────────────────────────────────

def _header_rows(family: str, lp, ctx: Dict[str, Any],
                 declared: Set[str]) -> List[Tuple[str, str]]:
    """Administrative values the template does not declare itself."""
    rows = []
    for label, field in HEADER_FIELDS:
        if field in declared:
            continue
        raw = getattr(lp, field, None)
        if isinstance(raw, (int, float)) and raw <= 0:
            continue
        value = _value_for(family, field, lp, ctx)
        if value:
            rows.append((label, value))
    return rows


def _resource_lines(lp) -> List[str]:
    """Source + teacher resources as one honest list (never fabricated)."""
    from ..ai_resource_text import normalize_text_items

    source = normalize_text_items(getattr(lp, "source_tlrs", None))
    teacher = normalize_text_items(getattr(lp, "other_tlrs", None))
    display = normalize_text_items(
        getattr(lp, "teaching_learning_resources", None))
    # LESSON VALUE WINS (PART 13/26): the teacher-editable lesson list is
    # authoritative when the teacher has edited it; the source record remains
    # the fallback and is never mutated. Keeps the PDF's Resources cell
    # identical to the DOCX renderers, which already read this field.
    pool = display or source or []
    extra = [r for r in teacher if r.lower() not in {p.lower() for p in pool}]
    return pool + extra


#: Activity-list fields a standard template's own sections declare.
_ACTIVITY_LIST_FIELDS = frozenset(
    {"main_activities", "learner_activities", "teacher_activities"})


def _activity_rows(items: Sequence[Any]) -> List[Tuple[str, str, str]]:
    """(Phase, Duration, Activity) rows for one stored activity list."""
    rows: List[Tuple[str, str, str]] = []
    for act in items or []:
        if isinstance(act, dict):
            def get(name, act=act):
                return act.get(name)
        else:
            def get(name, act=act):
                return getattr(act, name, None)
        description = _text(get("description") or get("text"))
        if not description:
            continue
        duration = get("duration_minutes")
        rows.append((_text(get("phase")) or "-",
                     str(duration) if duration else "",
                     description))
    return rows


# ── renderer ─────────────────────────────────────────────────────────────────

class StructuredPDFEngine:
    """Render lesson plans to a structured, template-aware PDF."""

    def render(self, lesson_plans, template: Optional[Template] = None,
               output_path: Optional[Path] = None,
               render_context: Optional[Dict[str, Any]] = None) -> Path:
        lessons: List[LessonPlan] = list(lesson_plans or [])
        if not lessons:
            raise PDFRenderError("no lesson plans to render")
        output_path = Path(output_path or f"lesson_plan_{lessons[0].id}.pdf")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        ctx = dict(render_context or {})
        family, sections = _plan_for(template)

        story: List[Any] = []
        for index, lp in enumerate(lessons):
            if index:
                story.append(PageBreak())
            story.extend(self._lesson_story(lp, sections, family, ctx))

        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            leftMargin=MARGIN_MM * mm,
            rightMargin=MARGIN_MM * mm,
            topMargin=MARGIN_MM * mm,
            bottomMargin=MARGIN_MM * mm,
            title=_TITLE_TEXT,
        )
        try:
            doc.build(story)
        except Exception as exc:  # never hand a broken body to the caller
            raise PDFRenderError(f"structured PDF build failed: {exc}") from exc
        if not _has_pdf_signature(output_path):
            raise PDFRenderError("structured renderer produced a non-PDF file")
        return output_path

    # ── Story assembly ────────────────────────────────────────────────────

    def _lesson_story(self, lp, sections, family: str,
                      ctx: Dict[str, Any]) -> List[Any]:
        story: List[Any] = [Paragraph(_TITLE_TEXT, _TITLE_STYLE)]
        state: Dict[str, Any] = {"shown": set(), "resources": False}
        declared = _declared_fields(sections)

        if not any(s["name"] in HEADER_SECTION_NAMES for s in sections):
            rows = _header_rows(family, lp, ctx, declared)
            if rows:
                story.append(Paragraph("Lesson Plan Header", _SECTION_STYLE))
                story.append(_kv_table(rows))

        for section in sections:
            name = section["name"]
            rows: List[Tuple[str, str]] = []
            grid: Optional[List[Tuple[str, str, str]]] = None

            if name in DELIVERY_SECTION_NAMES:
                rows, grid = self._render_delivery(section, lp, family, ctx,
                                                   state)
                if not rows and not grid:
                    continue
            else:
                rows = self._field_rows(section, lp, family, ctx, state)
                if name in HEADER_SECTION_NAMES:
                    rows.extend(_header_rows(family, lp, ctx, declared))
                elif name == "introduction":
                    rows.extend(self._starter_row(lp, family, ctx, state))
                if not rows and self._section_fully_shown(section, state):
                    continue

            story.append(Paragraph(section["label"], _SECTION_STYLE))
            if rows:
                story.append(_kv_table(rows))
            if grid:
                story.append(Spacer(1, 4))
                story.append(_activity_table(grid))

        story.extend(self._assignment_story(lp, family, ctx, state))
        story.extend(self._reference_story(lp, family, ctx, state))
        return story

    @staticmethod
    def _render_delivery(section, lp, family, ctx, state):
        """One section's delivery body: the form's own cells, or its grid."""
        if section["name"] in MERGED_DELIVERY_NAMES:
            return _merged_rows(section, lp, family, ctx, state), None
        return _split_delivery(section, lp, family, ctx, state)

    @staticmethod
    def _field_rows(section, lp, family, ctx, state) -> List[Tuple[str, str]]:
        rows: List[Tuple[str, str]] = []
        for field in section.get("fields", []):
            name = field.get("field")
            if not name or name in state["shown"]:
                continue
            label = field.get("label") or name
            value = _value_for(family, name, lp, ctx, label, authoritative=True)
            if not value:
                continue
            state["shown"].add(name)
            if name == "teaching_learning_resources":
                state["resources"] = True
            rows.append((label, value))
        return rows

    @staticmethod
    def _starter_row(lp, family, ctx, state) -> List[Tuple[str, str]]:
        if "starter_activity" in state["shown"]:
            return []
        value = _value_for(family, "starter_activity", lp, ctx)
        if not value:
            return []
        state["shown"].add("starter_activity")
        return [("Starter Activity", value)]

    @staticmethod
    def _section_fully_shown(section, state) -> bool:
        fields = [f.get("field") for f in section.get("fields", [])
                  if f.get("field")]
        return bool(fields) and all(name in state["shown"] for name in fields)

    def _assignment_story(self, lp, family, ctx, state) -> List[Any]:
        rows = []
        for label, field in _ASSIGNMENTS:
            if field in state["shown"]:
                continue
            value = _value_for(family, field, lp, ctx)
            if value:
                state["shown"].add(field)
                rows.append((label, value))
        if not rows:
            return []
        return [Paragraph("Assignments", _SECTION_STYLE), _kv_table(rows)]

    def _reference_story(self, lp, family, ctx, state) -> List[Any]:
        story: List[Any] = []
        if "references" not in state["shown"]:
            # A form cell (the GES "Reference" cell) may already have printed
            # them: the same teacher content never appears twice on a page.
            structured = list(getattr(lp, "structured_references", None) or [])
            flat = list(getattr(lp, "references", None) or [])
            if structured:
                story.append(Paragraph("References", _SECTION_STYLE))
                story.append(_reference_table(structured))
            elif flat:
                state["shown"].add("references")
                story.append(Paragraph("References", _SECTION_STYLE))
                story.append(_kv_table([("References", _join_lines(flat))]))
        if not state["resources"]:
            resources = _resource_lines(lp)
            if resources:
                story.append(Paragraph("Teaching & Learning Resources",
                                       _SECTION_STYLE))
                story.append(_kv_table([("Resources", _join_lines(resources))]))
        return story


def _merged_rows(section, lp, family, ctx, state) -> List[Tuple[str, str]]:
    """Rows for a one-section delivery form (GES / WAPEF), in field order.

    Each row is one of the form's own labelled cells, resolved through that
    template's resolver, so e.g. the WAPEF shared resource list lands in the
    MAIN row only and the GES plenary carries reflection + homework.
    """
    rows: List[Tuple[str, str]] = []
    for field in section.get("fields", []):
        name = field.get("field")
        if not name or name in state["shown"]:
            continue
        label = field.get("label") or name
        value = _value_for(family, name, lp, ctx, label, authoritative=True)
        if not value:
            continue
        state["shown"].add(name)
        if name == "teaching_learning_resources":
            state["resources"] = True
        for alias in _COMPOSED_FIELDS.get(family, {}).get(name, ()):
            state["shown"].add(alias)
        rows.append((label, value))
    return rows


def _split_delivery(section, lp, family, ctx, state
                    ) -> Tuple[List[Tuple[str, str]],
                               Optional[List[Tuple[str, str, str]]]]:
    """Standard templates: each activity list gets its own section and grid.

    The standard renderer keeps Main / Learner / Teacher activities in three
    separate sections, so each one prints only its own list — never the whole
    lesson repeated under three headings.
    """
    rows: List[Tuple[str, str]] = []
    grid: List[Tuple[str, str, str]] = []
    fields = section.get("fields") or [{"field": section["name"],
                                        "label": section["label"]}]
    for field in fields:
        name = field.get("field")
        if not name or name in state["shown"]:
            continue
        if name in _ACTIVITY_LIST_FIELDS:
            items = list(getattr(lp, name, None) or [])
            if not items:
                continue
            state["shown"].add(name)
            grid.extend(_activity_rows(items))
            continue
        label = field.get("label") or name
        value = _value_for(family, name, lp, ctx, label, authoritative=True)
        if not value:
            continue
        state["shown"].add(name)
        if name == "teaching_learning_resources":
            state["resources"] = True
        rows.append((label, value))
    return rows, grid or None


def _has_pdf_signature(path: Path) -> bool:
    try:
        with Path(path).open("rb") as handle:
            return handle.read(len(_PDF_MAGIC)) == _PDF_MAGIC
    except OSError:
        return False


def render_structured_pdf(lesson_plans, template=None, output_path=None,
                          render_context=None) -> Path:
    """Render lesson plans to a structured PDF; raises PDFRenderError."""
    return StructuredPDFEngine().render(
        lesson_plans, template=template, output_path=output_path,
        render_context=render_context)

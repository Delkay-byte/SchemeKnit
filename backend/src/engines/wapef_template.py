"""
Approved WAPEF Plan — lesson-plan template (in-place renderer).

SOURCE OF TRUTH: the WAPEF Approved Plan document supplied by WAPEF, bundled
verbatim at ``backend/src/engines/assets/wapef_approved_plan_template.docx``
(the supplied plan with blank value cells tokenized — every table, row, column
width, merge and label is the source's own).

This module NEVER hand-writes the WAPEF form's topology. The bundled .docx IS
the document: the renderer fills its bracketed tokens in place (one form block
per lesson), so a generated plan is topologically identical to the approved
source by construction — the same approach the official GES forms use
(``official_ges_template.py``).

Contract (mirrors the GES form contract):
- Administrative and curriculum fields are DETERMINISTIC-ONLY: they resolve
  from the stored lesson and never from AI.
- The four WAPEF fields (Deep Hope, Storyline, Through lines, God's Story) are
  TEACHER-SELECTED structured values (see ``wapef_fields.py``). Generation may
  pass them as instructional context but the export always renders the stored
  selection verbatim; blank stays blank — never invented, never rewritten.
- A field with nothing to resolve renders blank. Nothing is invented.
"""

from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

from .official_ges_template import (
    _code_and_text,
    _fill_paragraph,
    _iter_paragraphs,
    _sectpr,
    PLACEHOLDER_RE,
    activity_rows,
    row_description,
    row_in_phase,
)
from .wapef_fields import (
    format_through_lines,
    normalize_through_lines,
)

TEMPLATE_VERSION = "1.0"

TEMPLATE_ID = "tpl-wapef-approved-plan"
TEMPLATE_NAME = "Approved WAPEF Plan"

#: The approved WAPEF source document, bundled verbatim. Repo-relative path
#: used by the provenance registry and the acceptance report.
SOURCE_DOCUMENT = "backend/src/engines/assets/wapef_approved_plan_template.docx"

ASSETS_DIR = Path(__file__).resolve().parent / "assets"

#: Phase labels exactly as printed in the source's delivery tables (used
#: verbatim in the AI prompt; never invented).
WAPEF_PHASE_NAMES = (
    "PHASE 1 (STARTER)",
    "PHASE 2 (MAIN)",
    "PHASE 3 (PLENARY / REFLECTION)",
)


def template_path() -> Path:
    return ASSETS_DIR / "wapef_approved_plan_template.docx"


# ── Token contract ────────────────────────────────────────────────────────────

#: One entry per bracketed token in the bundled form: the canonical lesson
#: field it resolves from (None = renders blank unless the context supplies it,
#: e.g. REMARKS which the teacher may fill in review).
WAPEF_TOKEN_FIELDS: Dict[str, Optional[str]] = {
    "WEEK": "week_number",
    "WEEK_ENDING": "week_ending",
    "SUBJECT": "subject",
    "CLASS": "class_level",
    "CLASS_SIZE": "class_size",
    "STRAND": "strand",
    "SUB_STRAND": "sub_strand",
    "CONTENT_STANDARD": "content_standard",
    "LEARNING_INDICATOR": "learning_indicator",
    "PERFORMANCE_INDICATOR": "performance_indicator",
    "CORE_COMPETENCIES": "core_competencies",
    "KEY_WORDS": "keywords",
    "THROUGH_LINE": "wapef_through_lines",
    "GODS_STORY": "wapef_gods_story",
    "DEEP_HOPE": "wapef_deep_hope",
    "STORYLINE": "wapef_storyline",
    "PHASE_1_STARTER": "phase_1_activities",
    "PHASE_1_RESOURCES": "phase_1_resources",
    "PHASE_2_MAIN": "phase_2_activities",
    "PHASE_2_RESOURCES": "phase_2_resources",
    "PHASE_3_PLENARY": "phase_3_activities",
    "PHASE_3_RESOURCES": "phase_3_resources",
    "EVALUATION": "assessment",
    "REMARKS": "remarks",
}

WAPEF_TOKENS: List[str] = list(WAPEF_TOKEN_FIELDS)


def is_wapef_template(template) -> bool:
    """True when ``template`` (a Template, a template id, or None) is the
    Approved WAPEF Plan."""
    if template is None:
        return False
    ident = template if isinstance(template, str) else getattr(template, "id", None)
    return ident == TEMPLATE_ID


# ── Deterministic value resolution ────────────────────────────────────────────

def _get(lesson, name: str, default=None):
    if isinstance(lesson, dict):
        return lesson.get(name, default)
    return getattr(lesson, name, default)


def _text(value) -> str:
    """Plain string for a stored value, unwrapping enums."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(getattr(value, "value", value))


def _text_items(value) -> List[str]:
    """Stored JSON column (list | JSON string | text | None) -> list[str].

    CANONICAL (PART 6/9/11): delegates to the repository-wide normalizer so a
    comma-joined/serialized/empty-dirty stored value becomes individual clean
    items — and an empty value stays truly empty (never [\"\"] or [,]).
    """
    import json

    if value is None or value == "":
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text[0] in "[{":
            try:
                value = json.loads(text)
            except Exception:
                # Not parseable as JSON — fall through to the canonical
                # normalizer, which unwraps brackets and splits safely.
                pass
        else:
            # Plain multi-line text keeps its line structure first; the
            # normalizer then cleans any residual serialization damage.
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            from ..ai_resource_text import normalize_text_items
            out: List[str] = []
            for line in lines:
                out.extend(normalize_text_items(line))
            return out
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return _text_items(str(value))
    out = []
    for item in value:
        if item is None:
            continue
        if isinstance(item, str):
            out.append(item.strip())
        elif isinstance(item, dict):
            desc = item.get("description") or item.get("text") or item.get("title") or ""
            out.append(str(desc).strip())
        else:
            out.append(str(getattr(item, "description", item)).strip())
    from ..ai_resource_text import normalize_text_items
    return normalize_text_items([x for x in out if x])


def _bullet_block(lines: List[str]) -> str:
    return "\n".join(f"- {line}" for line in lines if line)


def _ordinal(day: int) -> str:
    if 11 <= day % 100 <= 13:
        return f"{day}th"
    return f"{day}{({1: 'st', 2: 'nd', 3: 'rd'}).get(day % 10, 'th')}"


def format_wapef_date(value) -> str:
    """``date`` -> "12-06-2026" (the WAPEF sample's own date style)."""
    if value is None or not hasattr(value, "strftime"):
        return ""
    try:
        return value.strftime("%d-%m-%Y")
    except Exception:
        return ""


def _activities_lines(lesson, *names: str, phase_index: Optional[int] = None) -> List[str]:
    """Description lines from one or more activity list fields.

    Activity descriptions are SENTENCES ("In pairs, learners sort the cards,
    then explain the rule") — the list normalizer that is right for resources
    would shatter them into comma fragments on the form, so each row's own
    description is read whole.
    """
    lines: List[str] = []
    for name in names:
        for item in activity_rows(lesson, name):
            if phase_index is not None and not row_in_phase(item, phase_index):
                continue
            desc = row_description(item)
            if desc and desc not in lines:
                lines.append(desc)
    return lines


def _prose_lines(lesson, *names: str) -> List[str]:
    """PROSE fields read verbatim — punctuation and all.

    ``_text_items`` is the resource/competency-list normalizer: it splits a
    serialized list on commas and semicolons. That is right for
    "Counters, sticks, flash cards" and destructive for a sentence — the
    teacher's Class Assignment

        "In pairs, learners classify a set of device pictures ...; the teacher
         checks the reasons given."

    came back as comma-less fragments joined into one run-on line in both the
    DOCX and the PDF. A sentence is not a list, so prose fields (starter,
    conclusion, class/home assignment, homework) are read whole.
    """
    out: List[str] = []
    for name in names:
        value = _get(lesson, name)
        if isinstance(value, (list, tuple)):
            text = "\n".join(str(v).strip() for v in value if str(v).strip())
        else:
            text = str(value or "").strip()
        for line in text.splitlines():
            line = line.strip()
            if line and line not in out:
                out.append(line)
    return out


def _phase_block(lesson, phase_index: int) -> str:
    """Learner-activity block for one WAPEF delivery phase.

    The source structure is one LEARNER ACTIVITIES column per phase row, so
    the lesson's phases map positionally: starter -> introduction/starter,
    main -> main/learner activities, plenary -> assessment/conclusion. Each
    cell shows ITS OWN phase only (see ``row_in_phase``): the stored boundary
    rows that keep the timeline's minutes exact render in their phase cell,
    never inside the neighbouring one.
    """
    if phase_index == 1:
        lines = _prose_lines(lesson, "introduction", "starter_activity")
        lines += _activities_lines(lesson, "learner_activities", phase_index=1)
    elif phase_index == 2:
        lines = _activities_lines(
            lesson, "learner_activities", "main_activities", phase_index=2)
        # PART 15: the approved form has no dedicated assignment row, so the
        # IN-LESSON assignment is placed in the MAIN phase it belongs to. It is
        # labelled so a reader can tell the task from the activities.
        class_task = " ".join(_prose_lines(lesson, "class_assignment")).strip()
        if class_task and class_task not in "\n".join(lines):
            lines = lines + [f"Class Assignment: {class_task}"]
    else:
        lines = _prose_lines(lesson, "conclusion")
        lines += _activities_lines(lesson, "learner_activities", phase_index=3)
        # PART 15: the follow-up task sits in the PLENARY / REFLECTION phase,
        # the form's own place for setting work after the lesson.
        home_task = " ".join(
            _prose_lines(lesson, "home_assignment", "homework")).strip()
        if home_task and home_task not in "\n".join(lines):
            lines = lines + [f"Home Assignment: {home_task}"]
    return _bullet_block([l for l in lines if l])


def _phase_resources(lesson, phase_index: int, ctx: Dict[str, Any]) -> str:
    """Phase RESOURCES cell.

    SOURCE resources from the scheme are preserved exactly once per lesson:
    the source convention keeps one shared list, so it is rendered in the MAIN
    (teaching-resources) row only. Repeating the identical list in every phase
    row would triple-count one resource set inside a single lesson. Teacher
    per-phase extras (other_tlrs) still appear on their own phase.
    """
    if phase_index != 2:
        # Phase 1/3 carry no separate resource list in the source convention.
        return ""
    source = _text_items(_get(lesson, "source_tlrs"))
    teacher = _text_items(_get(lesson, "other_tlrs"))
    display = _text_items(_get(lesson, "teaching_learning_resources"))
    # LESSON VALUE WINS (PART 13/26): ``teaching_learning_resources`` is the
    # teacher-editable lesson list — a corrected spelling ("Touchscreen")
    # replaces the source's own ("Touchscreenn") in the export while
    # ``source_tlrs`` keeps the scheme's verbatim record untouched. The source
    # list is the fallback for lessons the teacher has not edited.
    pool = display or source or []
    extra = [r for r in teacher if r.lower() not in {p.lower() for p in pool}]
    items = pool + extra
    if not items:
        return ""
    return "\n".join(f"- {r}" for r in items)


def _resolve(token: str, lesson, ctx: Dict[str, Any]) -> str:
    """Resolve one WAPEF token to the text the form expects.

    Blank means "SchemeKnit holds nothing for this" — never a placeholder.
    """
    field = WAPEF_TOKEN_FIELDS.get(token)
    if not field:
        return ""
    if field == "week_number":
        week = _get(lesson, "week_number")
        return _text(week) if week not in (None, "", 0) else ""
    if field == "week_ending":
        # Source-authoritative date first; a stored lesson_date is NOT
        # substituted (the WAPEF plan's Ending is the curriculum week-ending).
        return format_wapef_date(_get(lesson, "week_ending"))
    if field == "subject":
        return _text(_get(lesson, "subject"))
    if field == "class_level":
        return _text(_get(lesson, "class_level"))
    if field == "class_size":
        size = _get(lesson, "class_size")
        return _text(size) if size not in (None, "", 0) else ""
    if field == "strand":
        return _text(_get(lesson, "strand"))
    if field == "sub_strand":
        return _text(_get(lesson, "sub_strand"))
    if field == "content_standard":
        return _code_and_text(_get(lesson, "content_standard_code"),
                              _get(lesson, "content_standard"))
    if field == "learning_indicator":
        # Source indicator(s): codes where the scheme supplied them; plain
        # text when it did not (Nursery). Never a fabricated code.
        codes = _text_items(_get(lesson, "indicator_codes"))
        texts = _text_items(_get(lesson, "indicators"))
        if not texts:
            # Nursery-style rows may carry the sub-strand as the only focus.
            return ""
        out = []
        for i, text in enumerate(texts):
            code = codes[i] if i < len(codes) else ""
            if code and text.lower().startswith(code.lower()):
                out.append(text)
            else:
                out.append(_code_and_text(code, text))
        return "\n".join(out)
    if field == "performance_indicator":
        return _text_items_join(_get(lesson, "learning_objectives"))
    if field == "core_competencies":
        return ", ".join(_text_items(_get(lesson, "core_competencies")))
    if field == "keywords":
        return ", ".join(_text_items(_get(lesson, "keywords")))
    # The four WAPEF selections. ``field`` is the canonical lesson attribute
    # name (``WAPEF_TOKEN_FIELDS`` maps token -> lesson field), so these read
    # the exact stored value: teacher selection wins, verbatim, approved order
    # for the multi-select Through lines — never rewritten, never invented.
    if field == "wapef_through_lines":
        lines = _text_items(_get(lesson, "wapef_through_lines"))
        return format_through_lines(normalize_through_lines(lines))
    if field == "wapef_gods_story":
        return _text(_get(lesson, "wapef_gods_story"))
    if field == "wapef_deep_hope":
        return _text(_get(lesson, "wapef_deep_hope"))
    if field == "wapef_storyline":
        return _text(_get(lesson, "wapef_storyline"))
    if field == "phase_1_activities":
        return _phase_block(lesson, 1)
    if field == "phase_1_resources":
        return _phase_resources(lesson, 1, ctx)
    if field == "phase_2_activities":
        return _phase_block(lesson, 2)
    if field == "phase_2_resources":
        return _phase_resources(lesson, 2, ctx)
    if field == "phase_3_activities":
        return _phase_block(lesson, 3)
    if field == "phase_3_resources":
        return _phase_resources(lesson, 3, ctx)
    if field == "assessment":
        return _text(_get(lesson, "assessment"))
    if field == "remarks":
        # Teacher-owned reflection field; blank when not written.
        return _text(ctx.get("remarks") or _get(lesson, "remarks"))
    return ""


def _text_items_join(value) -> str:
    parts = []
    for item in _text_items(value):
        desc = item
        if " (" in item and item.endswith(")"):
            desc = item.split(" (")[0]
        if desc:
            parts.append(desc)
    return "\n".join(parts)


def wapef_placeholder_values(lesson, context: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """Deterministic ``token -> text`` map for one lesson."""
    ctx = context or {}
    return {token: _resolve(token, lesson, ctx) for token in WAPEF_TOKEN_FIELDS}


# ── Rendering ─────────────────────────────────────────────────────────────────

def load_wapef_document():
    """Open the bundled WAPEF form as a python-docx Document."""
    from docx import Document

    path = template_path()
    if not path.is_file():
        raise FileNotFoundError(f"WAPEF template missing: {path}")
    return Document(str(path))


def render_header(document, lesson, context: Optional[Dict[str, Any]] = None) -> None:
    """Fill the school / facilitator header lines above the metadata table.

    The supplied form prints the school name, the facilitator line and the
    LESSON PLAN title. Identity is server-derived (never client-supplied);
    lines with nothing to show stay blank.
    """
    ctx = context or {}
    school = _text(ctx.get("school_name") or _get(lesson, "school_name"))
    teacher = _text(ctx.get("teacher_name") or _get(lesson, "teacher_name"))
    term = _text(ctx.get("term") or _get(lesson, "term"))

    # The source prints exactly: [0] school line, [1] FACILITATOR line,
    # [2] LESSON PLAN title. The tokenized asset keeps that shape with the
    # school / facilitator identities blanked, so fill paragraphs 0 and 1
    # positionally and leave the title alone.
    paragraphs = list(document.paragraphs)
    if len(paragraphs) >= 1:
        _fill_paragraph(paragraphs[0], school)
    if len(paragraphs) >= 2:
        facilitator = f"FACILITATOR: {teacher}" if teacher else ""
        _fill_paragraph(paragraphs[1], facilitator)
    _ = term  # reserved: the source prints no term line; never add one


def render_into(document, lesson, context: Optional[Dict[str, Any]] = None,
                table_offset: int = 0) -> int:
    """Fill every placeholder of one WAPEF form for one lesson.

    Returns the number of tokens filled. Safe to call again on a cloned block
    (already-filled paragraphs hold no tokens).
    """
    ctx = context or {}
    values = wapef_placeholder_values(lesson, ctx)
    filled = 0
    for paragraph in _iter_paragraphs(document):
        tokens = PLACEHOLDER_RE.findall(paragraph.text or "")
        if not tokens:
            continue
        parts = [values.get(token, "") for token in tokens]
        _fill_paragraph(paragraph, "\n".join(p for p in parts if p))
        filled += len(tokens)
    return filled


def render_document(lesson_plans: List[Any], context: Optional[Dict[str, Any]] = None):
    """One Document holding one complete WAPEF form per lesson, each on its
    own page.

    The form block is cloned per lesson because a token can only be filled
    once — the same approach ``official_ges_template.render_document`` uses.
    """
    from docx.enum.text import WD_BREAK

    lessons = list(lesson_plans or [])
    document = load_wapef_document()
    if not lessons:
        return document

    body = document.element.body
    block = [deepcopy(el) for el in body if el is not _sectpr(body)]
    render_into(document, lessons[0], context, table_offset=0)
    render_header(document, lessons[0], context)

    for lesson in lessons[1:]:
        page_break = document.add_paragraph()
        page_break.add_run().add_break(WD_BREAK.PAGE)
        for element in block:
            _sectpr(body).addprevious(deepcopy(element))
        render_into(document, lesson, context, table_offset=0)
        render_header(document, lesson, context)

    return document


def validate_rendered_document(document) -> List[str]:
    """Any placeholder left unfilled (empty list means a clean form)."""
    leftovers = []
    for paragraph in _iter_paragraphs(document):
        leftovers.extend(PLACEHOLDER_RE.findall(paragraph.text or ""))
    return leftovers


# ── AI contract (activity-family fields only) ─────────────────────────────────

_WAPEF_RULES = """STRICT RULES (they mirror the approved WAPEF plan):
1. Return ONLY a flat JSON object matching the approved lesson schema (no markdown fences).
2. Allowed keys ONLY: lesson_topic, performance_indicator, core_competencies,
   new_words, phases, assessment, reflection, homework.
3. NEVER invent curriculum facts: no strands, standards, indicators, codes, dates,
   class sizes, or resource titles. Those come from the scheme of work.
4. NEVER output a Deep Hope, Storyline, Through line or God's Story value: those
   are teacher-selected structured fields and must never be chosen or rewritten by AI.
5. phases: use exactly the phase names supplied in the request. Do not invent extra phases.
6. Activities go ONLY in phases[].teacher_activities / learner_activities.
7. Assessment items ONLY in assessment. Plenary/reflection ONLY in reflection.
8. Keep the Ghanaian classroom context with limited resources. No projector/ICT assumptions.
9. Keep each string concise (single paragraph each); arrays hold separate items."""


def wapef_system_prompt() -> str:
    """System prompt for the Approved WAPEF Plan."""
    return (
        "You assist a Ghanaian teacher filling the Approved WAPEF Plan.\n"
        f"Required phase names: {', '.join(WAPEF_PHASE_NAMES)}\n"
        f"{_WAPEF_RULES}\n"
    )


def validate_wapef_lesson_json(data) -> tuple:
    """Validate AI output destined for the WAPEF plan.

    Same strict schema as the approved GES contract: every renderer reads the
    same stored lesson columns, and none may accept curriculum facts — or the
    four WAPEF selections — from a model response. Returns
    ``(ok, normalized | errors)``; never raises.
    """
    from .approved_template import validate_approved_lesson_json

    ok, result = validate_approved_lesson_json(data)
    if ok and isinstance(result, dict):
        # Defence in depth: strip any WAPEF field a model emitted anyway.
        for key in ("deep_hope", "storyline", "through_lines", "gods_story",
                    "through_line", "god's story"):
            result.pop(key, None)
    return ok, result

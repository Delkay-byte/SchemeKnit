"""
Official GES / NaCCA lesson plan templates — rendering engine.

Four official forms are bundled (verbatim, teacher supply) in ``assets/`` and
described by the level contracts in ``official_ges_levels.py``: Kindergarten,
Lower Primary, JHS and SHS. Each form is a *placeholder* document — bracketed
tokens (``[WEEK_ENDING]``, ``[PHASE_1_STARTER]``, ``[TUNING_IN_PHASE]`` …) inside
two tables — so this module fills the form in place rather than imitating its
layout with python-docx.

Two kinds of text in a source file must never reach a teacher's page:

1. Authoring guidance. The JHS form carries four numbered block headings with an
   "Instructions for AI Engine:" paragraph each, plus example bullets sharing a
   run with a phase token (``[PHASE_1_STARTER_ACTIVITIES]- Review prior
   knowledge.- Brain preparation hook.``). ``strip_guidance`` removes the blocks;
   the bullets vanish because filling a token rewrites its whole paragraph.
2. Example prose in delivery-grid columns that have no token (KG/Primary
   resource columns, the SHS learner and TLM columns). Those are declared as
   ``grid_fills`` in the level contract and overwritten from stored lesson data —
   blank when there is nothing to resolve.

Contract (same for every level):
- Administrative and curriculum fields are DETERMINISTIC-ONLY; they resolve from
  the stored lesson and never from AI.
- AI may contribute activity-family content only, through the validated JSON
  contract (``validate_ges_lesson_json``).
- A field with nothing to resolve renders blank. Nothing is invented.
"""

from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
import copy
import json
import re

from .official_ges_levels import (
    FILL_LEARNER,
    FILL_RESOURCES_AND_ASSESSMENT,
    GES_TEMPLATES,
    GESField,
    GESLevelSpec,
    JHS_SPEC,
    LEVEL_JHS,
    LEVEL_ORDER,
    SECTION_DELIVERY,
    SECTION_HEADER,
    SOURCE_AI,
    SOURCE_DETERMINISTIC,
    official_specs,
    spec_for_level,
    spec_for_template_id,
)

TEMPLATE_VERSION = "1.0"

#: Kept for backward compatibility with callers/tests that imported the old
#: blanket flag. The authoritative official/approved classification is the
#: provenance registry (template_provenance.py): all four bundled forms are
#: verified against their own GES/NaCCA source documents.
OFFICIAL_GES_CLAIM = True

ASSETS_DIR = Path(__file__).resolve().parent / "assets"

#: ``[WEEK_ENDING]`` / ``[PHASE_1_STARTER_ACTIVITIES]`` style tokens.
PLACEHOLDER_RE = re.compile(r"\[([A-Z][A-Z0-9_]*)\]")

#: Body-level authoring guidance in the JHS form: the four numbered block
#: headings and their "Instructions for AI Engine:" paragraphs.
GUIDANCE_HEADING_RE = re.compile(r"^\s*\d+\.\s+[A-Z][A-Z \-/&]+$")
GUIDANCE_PREFIX = "Instructions for AI Engine:"

# ── Reference spec (JHS) ──────────────────────────────────────────────────────
# The JHS form shipped first and its tokens are the ones the docs and tests
# quote, so it stays reachable as plain module constants.

TEMPLATE_ID = JHS_SPEC.template_id
TEMPLATE_NAME = JHS_SPEC.name
GES_FIELDS: List[GESField] = list(JHS_SPEC.fields)
GES_TOKENS: List[str] = JHS_SPEC.tokens
GES_PHASE_NAMES: Tuple[str, ...] = JHS_SPEC.phase_names


def template_source(spec: GESLevelSpec) -> str:
    """Evidence-based provenance line for one bundled form."""
    from .template_provenance import provenance_for_template

    record = provenance_for_template(spec.template_id)
    if record.official:
        return f"{spec.filename} (approved organizational source document, verified)"
    return f"{spec.filename} (teacher supply — PENDING SOURCE VERIFICATION)"


def template_path(spec: Optional[GESLevelSpec] = None) -> Path:
    """Absolute path of a bundled form (JHS by default)."""
    return ASSETS_DIR / (spec or JHS_SPEC).filename


def is_ges_form_template(template) -> bool:
    """True when ``template`` (a Template, a template id, or None) is any level's
    GES-style placeholder form, regardless of provenance.

    This is the *dispatch* predicate: these forms are rendered by the placeholder
    engine because their .docx assets are token documents. Approval classification
    is ``is_official_ges_template``.

    The approved organizational template id (``tpl-approved-org-headteacher``) is
    an alias of the verified JHS form: both name the same approved source
    document, so both must render that form in place. Routing the alias here is
    what keeps a single golden master instead of a second, drifting layout.
    """
    from .approved_template import TEMPLATE_ID as APPROVED_TEMPLATE_ID

    if template is None:
        return False
    ident = template if isinstance(template, str) else getattr(template, "id", None)
    if ident == APPROVED_TEMPLATE_ID:
        return True
    return spec_for_template_id(ident) is not None


def is_official_ges_template(template) -> bool:
    """True when ``template`` (a Template, a template id, or None) is a GES-form
    template that the provenance registry classifies as verified-approved.

    All four bundled level forms (KG, Lower Primary, JHS, SHS) are verified
    against their own GES/NaCCA source documents, so all qualify.
    """
    if not is_ges_form_template(template):
        return False
    ident = template if isinstance(template, str) else getattr(template, "id", None)
    from .template_provenance import provenance_for_template
    return provenance_for_template(ident).official


def sections_for(spec: GESLevelSpec) -> List[tuple]:
    """(section name, label, fields) groups for template registration."""
    from .official_ges_levels import SECTION_LABELS

    grouped: List[tuple] = []
    for field in spec.fields:
        if not grouped or grouped[-1][0] != field.section:
            grouped.append((field.section, SECTION_LABELS[field.section], []))
        grouped[-1][2].append(field)
    return grouped


# ── Deterministic value resolution ────────────────────────────────────────────

def _get(lesson, name: str, default=None):
    """Read a field from a pydantic lesson model or a plain dict."""
    if isinstance(lesson, dict):
        return lesson.get(name, default)
    return getattr(lesson, name, default)


def _text(value) -> str:
    """Plain string for a stored value, unwrapping enums.

    ``Subject.ICT`` / ``ClassLevel.BASIC_7`` stringify as "Subject.ICT" and
    "ClassLevel.BASIC_7" — the form must show the enum's value.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(getattr(value, "value", value))


def _text_items(value) -> List[str]:
    """Coerce a stored JSON column (list | JSON string | text | None) to strings.

    SQLite hands JSON columns back as strings on some paths and as lists on
    others; both shapes must render identically.
    """
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
                return [line.strip() for line in text.splitlines() if line.strip()]
        else:
            return [line.strip() for line in text.splitlines() if line.strip()]
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return [str(value)]
    out: List[str] = []
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
    return [x for x in out if x]


def _bullet_block(lines: Iterable[str]) -> str:
    """Turn step lines into the forms' dash-prefixed activity style."""
    return "\n".join(f"- {line}" for line in lines if line)


_ORDINAL_SUFFIXES = {1: "st", 2: "nd", 3: "rd"}


def _ordinal(day: int) -> str:
    """1 -> "1st", 12 -> "12th" (11-13 are always "th")."""
    if 11 <= day % 100 <= 13:
        return f"{day}th"
    return f"{day}{_ORDINAL_SUFFIXES.get(day % 10, 'th')}"


def format_long_date(value) -> str:
    """``date`` → "Friday, 25th September, 2026" (the JHS form's date style)."""
    if value is None or not hasattr(value, "strftime"):
        return ""
    return f"{value.strftime('%A')}, {_ordinal(value.day)} {value.strftime('%B')}, {value.year}"


def week_ending_for(lesson_date) -> str:
    """Friday of the lesson's own week, or "" when there is no date to derive it.

    Derived arithmetically from a stored date — never invented.
    """
    if lesson_date is None or not hasattr(lesson_date, "weekday"):
        return ""
    return format_long_date(lesson_date + timedelta(days=4 - lesson_date.weekday()))


def _join(items: List[str], separator: str = ", ") -> str:
    return separator.join(items)


def _code_and_text(code, text) -> str:
    code = _text(code).strip()
    text = _text(text).strip()
    if code and text:
        return f"{code} {text}"
    return code or text


_CODE_PREFIX_RE = re.compile(r'^\s*[Bb]?\d+(?:\.\d+){2,4}[.:]?\s*')


def _code_and_text_list(codes: List[str], texts: List[str]) -> List[str]:
    """Build ``code description`` pairs without duplication.

    When the stored text already begins with a code prefix the separate
    code entry is dropped so the code appears exactly once — matching the
    approved GES indicator cell format.
    """
    result: List[str] = []
    for i, text in enumerate(texts):
        if _CODE_PREFIX_RE.match(text):
            result.append(text)
        else:
            code = codes[i] if i < len(codes) else ""
            result.append(f"{code} {text}".strip() if code else text)
    return result


def _level_or_theme(lesson) -> str:
    """KG "Level / Theme" — the class and the curriculum theme, nothing added.

    e.g. "KG 2 / Our World Our People". Either part alone is shown alone; with
    neither there is nothing to show.
    """
    parts = [_text(_get(lesson, "class_level")).strip(), _text(_get(lesson, "strand")).strip()]
    return " / ".join(p for p in parts if p)


def _resolve(field: Optional[str], lesson, ctx: Dict[str, Any]) -> str:
    """Resolve one canonical field to the text a form expects.

    Blank means "SchemeKnit holds nothing for this" — never a placeholder value.
    """
    if not field:
        return ""
    if field == "week_ending":
        source = _get(lesson, "week_ending")
        if source is not None:
            return format_long_date(source)
        return week_ending_for(_get(lesson, "lesson_date"))
    if field == "lesson_date":
        return format_long_date(_get(lesson, "lesson_date"))
    if field == "class_level":
        return _text(_get(lesson, "class_level"))
    if field == "subject":
        return _text(_get(lesson, "subject"))
    if field == "class_size":
        size = _get(lesson, "class_size")
        return _text(size) if size not in (None, "", 0) else ""
    if field == "duration_minutes":
        duration = _get(lesson, "duration_minutes")
        return f"{_text(duration)} Minutes" if duration else ""
    if field == "period":
        # Timetable slot: not a stored lesson column, so it comes from the
        # caller's context or stays blank.
        return _text(ctx.get("period") or _get(lesson, "period"))
    if field == "programme":
        # SHS programme (Science, Business, Home Economics …): not stored.
        return _text(ctx.get("programme") or _get(lesson, "programme"))
    if field == "references":
        return _join(_text_items(_get(lesson, "references"))) or _text(ctx.get("reference"))
    if field == "strand":
        return _text(_get(lesson, "strand"))
    if field == "sub_strand":
        return _text(_get(lesson, "sub_strand"))
    if field == "content_standard":
        return _code_and_text(_get(lesson, "content_standard_code"),
                              _get(lesson, "content_standard"))
    if field == "indicators":
        codes = _text_items(_get(lesson, "indicator_codes"))
        texts = _text_items(_get(lesson, "indicators"))
        return _join(_code_and_text_list(codes, texts), "\n")
    if field == "core_competencies":
        return _join(_text_items(_get(lesson, "core_competencies")))
    if field == "learning_objectives":
        return _join(_text_items(_get(lesson, "learning_objectives")), "\n")
    if field == "keywords":
        return _join(_text_items(_get(lesson, "keywords")))
    if field == "teaching_learning_resources":
        return _join(_text_items(_get(lesson, "teaching_learning_resources")))
    if field == "previous_knowledge":
        return _text(_get(lesson, "previous_knowledge"))
    if field == "level_or_theme":
        return _level_or_theme(lesson)
    if field == "introduction":
        starter = (_text_items(_get(lesson, "introduction"))
                   or _text_items(_get(lesson, "starter_activity")))
        return _bullet_block(starter)
    if field == "main_activities":
        steps = (_text_items(_get(lesson, "main_activities"))
                 + _text_items(_get(lesson, "teacher_activities"))
                 + _text_items(_get(lesson, "learner_activities")))
        return _bullet_block(steps)
    if field == "assessment":
        return _text(_get(lesson, "assessment"))
    if field == "conclusion":
        close = (_text_items(_get(lesson, "conclusion"))
                 + _text_items(_get(lesson, "reflection"))
                 + _text_items(_get(lesson, "homework")))
        return _bullet_block(close)
    return ""


def _grid_value(kind: str, lesson, ctx: Dict[str, Any]) -> str:
    """Text for a delivery-grid cell that has no placeholder of its own."""
    if kind == FILL_LEARNER:
        return _bullet_block(_text_items(_get(lesson, "learner_activities")))
    if kind == FILL_RESOURCES_AND_ASSESSMENT:
        parts = [_join(_text_items(_get(lesson, "teaching_learning_resources"))),
                 _text(_get(lesson, "assessment"))]
        return "\n".join(p for p in parts if p)
    return ""


def placeholder_values(spec: GESLevelSpec, lesson,
                       context: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """Deterministic ``token -> text`` map for one lesson and one level.

    Values come from stored lesson columns only; a token with nothing to derive
    renders blank. ``context`` carries caller-known extras that are not lesson
    columns (``{"period": "1 & 2"}``, ``{"programme": "Science"}``, …) and never
    overrides a value found on the lesson itself.
    """
    ctx = context or {}
    return {field.token: _resolve(field.field, lesson, ctx) for field in spec.fields}


def normalize_lesson_to_ges(spec: GESLevelSpec, lesson,
                            context: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """Deterministic (no-AI) token -> text view of a stored lesson."""
    return placeholder_values(spec, lesson, context)


# ── Rendering ─────────────────────────────────────────────────────────────────

def load_document(spec: Optional[GESLevelSpec] = None):
    """Open a bundled form as a python-docx Document (JHS by default)."""
    from docx import Document

    path = template_path(spec)
    if not path.is_file():
        raise FileNotFoundError(f"Official GES template missing: {path}")
    return Document(str(path))


def _iter_paragraphs(container):
    """Every paragraph in a document/table cell, including nested tables."""
    for paragraph in container.paragraphs:
        yield paragraph
    for table in container.tables:
        for row in table.rows:
            for cell in row.cells:
                yield from _iter_paragraphs(cell)


#: The generic printed title on every bundled form. It is form boilerplate, not
#: planning context, so it is replaced with the actual school/term/week header
#: (see ``render_header``). Covers both printed wordings: the JHS form's
#: "OFFICIAL GES / NaCCA WEEKLY LESSON PLAN TEMPLATE" and the KG/Primary/SHS
#: forms' "GES/NaCCA <LEVEL> LESSON PLAN TEMPLATE". Matched on the fixed words
#: that identify the blank-form title, never on a school or teacher name.
GENERIC_TITLE_RE = re.compile(
    r"(?:OFFICIAL\s+)?GES\s*/\s*NaCCA\s+.*?LESSON\s+PLAN\s+TEMPLATE",
    re.IGNORECASE | re.DOTALL,
)


def _term_label(lesson, ctx: Dict[str, Any]) -> str:
    """Academic term as the header shows it.

    Never invented: the configured term wins, then a term carried on the lesson,
    then nothing (the line is omitted rather than guessed).
    """
    raw = ctx.get("academic_term") or _get(lesson, "academic_term")
    if not raw:
        return ""
    text = _text(raw).strip()
    if not text:
        return ""
    # "First Term" / "Second Term" … → "Term 1" / "Term 2" …, preserving any
    # wording the caller already supplied in the compact form.
    order = {"first": 1, "second": 2, "third": 3, "fourth": 4, "1": 1, "2": 2,
             "3": 3, "4": 4}
    first = text.split()[0].lower().rstrip(".")
    if first in order and not text.lower().startswith("term "):
        return f"Term {order[first]}"
    return text


def render_header(document, lesson, context: Optional[Dict[str, Any]] = None) -> bool:
    """Replace the form's generic template title with the real planning context.

    The bundled forms print ``OFFICIAL GES / NaCCA WEEKLY LESSON PLAN
    TEMPLATE`` at the top of the page. That is the form's own boilerplate: it
    describes the *blank form*, not the lesson, so a generated plan must show
    the actual context instead — the school, the term and week, the teacher and
    the class. Everything is read from the lesson/context, which the server
    derives from the authenticated user and the scheme allocation; nothing here
    is invented and no client-supplied identity is trusted.

    The replacement goes into the same paragraphs, keeping the form's own
    styles, so the approved table structure and layout are untouched (PART 19).

    Returns True when a title was replaced.
    """
    ctx = context or {}
    school = _text(ctx.get("school_name") or _get(lesson, "school_name"))
    teacher = _text(ctx.get("teacher_name") or _get(lesson, "teacher_name"))
    term = _term_label(lesson, ctx)
    week = _get(lesson, "week_number")
    week_text = f"Week {_text(week)}" if week not in (None, "", 0) else ""

    lines = []
    if school:
        lines.append(school)
    if term and week_text:
        lines.append(f"{term}. {week_text}")
    elif term:
        lines.append(term)
    elif week_text:
        lines.append(week_text)
    if not lines:
        return False

    replaced = False
    for paragraph in list(document.paragraphs):
        text = (paragraph.text or "").strip()
        if not text or not GENERIC_TITLE_RE.search(text):
            continue
        # Keep the paragraph's own style; only its wording changes.
        _fill_paragraph(paragraph, "\n".join(lines))
        replaced = True
        # The class/teacher line goes directly under the title in the same style
        # family, as a continuation paragraph, so it stays inside the header band.
        if teacher:
            new_p = copy.deepcopy(paragraph._element)
            paragraph._element.addnext(new_p)
            from docx.text.paragraph import Paragraph
            _fill_paragraph(Paragraph(new_p, paragraph._parent),
                            f"Teacher: {teacher}")
        break
    return replaced


def strip_guidance(document) -> int:
    """Remove the form's own authoring guidance; returns how many were removed.

    Drops the four numbered block headings and their "Instructions for AI
    Engine:" paragraphs (JHS form). The example bullets that share a run with a
    phase token are not touched here — filling the token rewrites that
    paragraph, so they cannot survive into a generated plan either.
    """
    removed = 0
    for paragraph in list(document.paragraphs):
        text = (paragraph.text or "").strip()
        if not text:
            continue
        if GUIDANCE_HEADING_RE.match(text) or text.startswith(GUIDANCE_PREFIX):
            paragraph._element.getparent().remove(paragraph._element)
            removed += 1
    return removed


def _fill_paragraph(paragraph, text: str) -> None:
    """Replace a paragraph's content with ``text``, keeping the first run's format.

    Rewriting the run (rather than only the token) is what removes the example
    bullets and line breaks that a form stores alongside each token.
    """
    runs = paragraph.runs
    if not runs:
        paragraph.add_run(text)
        return
    runs[0].text = text
    for extra in runs[1:]:
        extra._element.getparent().remove(extra._element)


def _set_cell_text(cell, text: str) -> None:
    """Replace a whole cell's content with ``text`` (used for grid fills)."""
    paragraphs = list(cell.paragraphs)
    if not paragraphs:
        return
    _fill_paragraph(paragraphs[0], text)
    for extra in paragraphs[1:]:
        extra._element.getparent().remove(extra._element)


def _apply_grid_fills(spec: GESLevelSpec, document, lesson, ctx: Dict[str, Any],
                      table_offset: int = 0) -> int:
    """Overwrite the untokened delivery-grid cells declared by the level contract."""
    applied = 0
    for fill in spec.grid_fills:
        try:
            cell = document.tables[table_offset + fill.table].cell(fill.row, fill.column)
        except (IndexError, KeyError):
            continue
        _set_cell_text(cell, _grid_value(fill.kind, lesson, ctx))
        applied += 1
    return applied


def render_into(spec: GESLevelSpec, document, lesson,
                context: Optional[Dict[str, Any]] = None,
                table_offset: int = 0) -> int:
    """Fill every placeholder (and declared grid cell) of one form for one lesson.

    Returns the number of tokens filled. Already-filled paragraphs hold no
    tokens, so this is safe to call again after cloning a form. ``table_offset``
    shifts grid-cell addressing in a document that holds several cloned copies
    (one per page).
    """
    ctx = context or {}
    values = placeholder_values(spec, lesson, ctx)
    filled = 0
    for paragraph in _iter_paragraphs(document):
        tokens = PLACEHOLDER_RE.findall(paragraph.text or "")
        if not tokens:
            continue
        parts = [values.get(token, "") for token in tokens]
        _fill_paragraph(paragraph, "\n".join(p for p in parts if p))
        filled += len(tokens)
    _apply_grid_fills(spec, document, lesson, ctx, table_offset)
    return filled


def _sectpr(body):
    from docx.oxml.ns import qn

    return body.find(qn("w:sectPr"))


def render_document(spec: GESLevelSpec, lesson_plans: List[Any],
                    context: Optional[Dict[str, Any]] = None):
    """One Document holding one complete official form per lesson, each on its
    own page.

    The form block is stripped once and then cloned per lesson: a token can only
    be filled once, so lessons after the first need their own copy of the form
    rather than the already-filled one.
    """
    from docx.enum.text import WD_BREAK

    lessons = list(lesson_plans or [])
    document = load_document(spec)
    strip_guidance(document)
    if not lessons:
        return document

    body = document.element.body
    tables_per_form = len(document.tables)
    block = [copy.deepcopy(el) for el in body if el is not _sectpr(body)]
    render_into(spec, document, lessons[0], context, table_offset=0)
    # The generic form title is replaced per-lesson with the real school /
    # term / week context, so each page carries its own planning header.
    render_header(document, lessons[0], context)

    for index, lesson in enumerate(lessons[1:], start=1):
        page_break = document.add_paragraph()
        page_break.add_run().add_break(WD_BREAK.PAGE)
        for element in block:
            _sectpr(body).addprevious(copy.deepcopy(element))
        render_into(spec, document, lesson, context, table_offset=index * tables_per_form)
        render_header(document, lesson, context)

    return document


def validate_rendered_document(document) -> List[str]:
    """Return any placeholder left unfilled (empty list means a clean form)."""
    leftovers = []
    for paragraph in _iter_paragraphs(document):
        leftovers.extend(PLACEHOLDER_RE.findall(paragraph.text or ""))
    return leftovers


# ── AI contract (activity-family fields only) ─────────────────────────────────

_GES_RULES = """STRICT RULES (they mirror the official GES/NaCCA form):
1. Return ONLY a flat JSON object matching the lesson schema (no markdown fences).
2. Allowed keys ONLY: lesson_topic, performance_indicator, core_competencies,
   references, new_words, phases, assessment, reflection, homework.
3. NEVER invent curriculum facts: no strands, standards, indicators, codes, dates,
   class sizes, durations, or resource titles. Those come from the scheme of work.
4. phases: use exactly the phase names supplied in the request. Do not invent extra phases.
5. Activities go ONLY in phases[].teacher_activities / learner_activities.
6. Starter and diagnostic resources go ONLY in phases[].resources; formative assessment
   items ONLY in assessment; plenary recap, exit-ticket prompts and teacher reflection
   ONLY in reflection; follow-up work ONLY in homework.
7. Keep the Ghanaian classroom context with limited resources. No projector, smartboard
   or internet assumptions.
8. Keep each string concise (single paragraph each); arrays hold separate items."""


def ges_system_prompt(spec: GESLevelSpec) -> str:
    """System prompt for one level: the shared rules plus the level framing.

    The level's printed phase row labels are stated explicitly, because rule 4
    tells the model to use the supplied names and each form names them
    differently (Tuning-In / Starter / Introduction / Starter-Intro).
    """
    return (
        "You assist a Ghanaian teacher filling the official GES/NaCCA weekly lesson plan.\n"
        f"{spec.prompt_tailoring}\n"
        f"Required phase names: {', '.join(spec.phase_names)}\n"
        f"{_GES_RULES}\n"
    )


#: JHS prompt, kept as a module constant alongside the JHS reference tokens.
GES_SYSTEM_PROMPT = ges_system_prompt(JHS_SPEC)


def validate_ges_lesson_json(data) -> tuple:
    """Validate AI output destined for any official GES form.

    Deliberately the same strict schema as the approved contract: every renderer
    reads the same stored lesson columns, and none may accept curriculum facts
    from a model response. Returns ``(ok, normalized | errors)``; never raises.
    """
    from .approved_template import validate_approved_lesson_json

    return validate_approved_lesson_json(data)

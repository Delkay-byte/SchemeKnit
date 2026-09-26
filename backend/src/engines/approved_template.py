"""
Approved Organizational Lesson-Plan Template (canonical golden master).

SOURCE OF TRUTH: the approved lesson-plan DOCX supplied by the
organization/headteacher, bundled verbatim at
``backend/src/engines/assets/ges_jhs_lesson_plan_template.docx``.

This module NEVER hand-writes the form's topology. ``build_approved_structure``
opens the real source document, strips its authoring guidance and derives the
TemplateStructure IR from it programmatically (tables, grid spans, merges,
labels, phase markers, activity-grid roles). The field mapping is then taken
from the source's own bracketed tokens, so field coordinates stay pinned to the
document rather than to a transcription that can drift.

The export path renders the source form *in place* — the bundled .docx is the
document and its placeholders are filled — so a generated plan is topologically
identical to the approved source by construction (see
``official_ges_template.render_document`` and the alias registered for this
template id). There is no second competing hand-written structure.

Measured structural fingerprint of the approved source (4 tables, no merges):

    TABLE 0  administrative metadata   4 rows x 4 grid cols
    TABLE 1  curriculum alignment      4 rows x 2 grid cols
    TABLE 2  pedagogical foundations   4 rows x 2 grid cols
    TABLE 3  tridelivery timeline      4 rows x 3 grid cols
             header: PHASE / TIMELINE | LEARNER & TEACHER ACTIVITIES | TLRs / ASSESSMENT
             PHASE 1: STARTER / INTRO    (10 Mins)
             PHASE 2: MAIN LEARNING      (40 Mins)
             PHASE 3: PLENARY / REFLECTION (10 Mins)

Note on phase durations: the printed "(10 Mins)" / "(40 Mins)" / "(10 Mins)"
values are part of the SOURCE DOCUMENT's own phase-cell text. They are
preserved verbatim by the in-place renderer; SchemeKnit does not compute, assert
or hardcode any phase split — it does not decide that a starter must be 10
minutes. Where a stored lesson carries its own duration, that is rendered in the
administrative Duration field.

PROVENANCE: the source document is the approved organizational template. Its
own printed title reads "OFFICIAL GES / NaCCA WEEKLY LESSON PLAN TEMPLATE";
that text is the document's, reproduced verbatim, and is not an independent
SchemeKnit claim of NaCCA endorsement. See ``template_provenance.py``.
"""

import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator

from .official_ges_levels import JHS_SPEC
from .official_ges_template import (
    PLACEHOLDER_RE, load_document, strip_guidance,
)
from .template_analyzer import analyze_docx_document

TEMPLATE_ID = "tpl-approved-org-headteacher"
#: Retired display name (PART B/C): the legacy "Headteacher Source" wording is
#: gone. This id is an internal alias of the Approved GES Plan (JHS form) and
#: is no longer selectable; the name below is only used in diagnostics.
TEMPLATE_NAME = "Approved Organizational Lesson Plan (retired alias)"
TEMPLATE_VERSION = "1.0"

#: The approved source document, bundled verbatim. Repo-relative path used by
#: the provenance registry and the acceptance report.
SOURCE_DOCUMENT = "backend/src/engines/assets/ges_jhs_lesson_plan_template.docx"

#: Phase row labels exactly as printed in the source's delivery table (the
#: duration line is a separate paragraph in the same cell, so the marker is the
#: first line). Derived from the source, never invented.
APPROVED_PHASE_NAMES = tuple(JHS_SPEC.phase_names)


def _token_field_map() -> Dict[str, Optional[str]]:
    """``TOKEN`` -> canonical SchemeKnit field, from the level contract.

    The approved form's placeholders are the authoritative pin between a cell
    coordinate and a stored field, so the mapping cannot drift from the
    document the way a label heuristic can.
    """
    return {field.token: field.field for field in JHS_SPEC.fields}


def _apply_token_fields(structure: Dict) -> None:
    """Re-map label cells to fields using the source's own bracketed tokens.

    The approved form puts a label in one cell and its placeholder in the next
    (``WEEK ENDING:`` then ``[INSERT_WEEK_ENDING]``), and the analyzer's label
    heuristics miss some ("TEACHING & LEARNING RESOURCES (TLRs)"). The token
    inside a value cell names its field exactly, so:

    1. every cell holding a ``[TOKEN]`` is pinned to that token's field;
    2. each such field is propagated back to the label cell that precedes it in
       the same row, which is what the consolidated mapping list is built from.

    A cell with no token keeps the analyzer's mapping (custom-keep when
    unknown), so nothing is silently dropped.
    """
    token_map = _token_field_map()
    for table in structure.get("tables", []):
        cells = table.get("cells", [])
        # row -> ordered cells, to locate the label preceding each value cell.
        by_row: Dict[int, List[Dict]] = {}
        for cell in cells:
            by_row.setdefault(cell.get("r", 0), []).append(cell)

        for row_cells in by_row.values():
            last_label_cell: Optional[Dict] = None
            for cell in row_cells:
                if cell.get("covered") or cell.get("is_phase_marker"):
                    continue
                label = cell.get("label")
                text = cell.get("text") or ""
                match = PLACEHOLDER_RE.search(text)
                if match:
                    field = token_map.get(match.group(1))
                    cell["field"] = field
                    cell["confidence"] = "high"
                    cell["match_kind"] = "token"
                    cell["custom"] = field is None
                    cell["sample_value"] = ""
                    if label is None and last_label_cell is not None:
                        # Separate label/value cells: pin the label cell too.
                        last_label_cell["field"] = field
                        last_label_cell["confidence"] = "high"
                        last_label_cell["match_kind"] = "token"
                        last_label_cell["custom"] = field is None
                elif label:
                    last_label_cell = cell

    # Rebuild the consolidated mapping list from the token-pinned label cells.
    mappings: List[Dict] = []
    seen = set()
    for table in structure.get("tables", []):
        for cell in table.get("cells", []):
            if cell.get("covered") or cell.get("is_phase_marker"):
                continue
            label = cell.get("label")
            if not label or label in seen:
                continue
            # A value cell (no label) already contributed via its label cell.
            if not cell.get("label"):
                continue
            seen.add(label)
            mappings.append({
                "label": label,
                "field": cell.get("field"),
                "confidence": cell.get("confidence", "manual"),
                "match_kind": cell.get("match_kind", "none"),
                "custom": cell.get("custom", False),
                "teacher_confirmed": True,
            })
    structure["mappings"] = mappings


def _source_paragraph_lines() -> List[str]:
    """Title lines printed above the tables, with guidance blocks removed.

    The source carries a single title line; numbered guidance blocks are
    dropped so they never reach a teacher's plan.
    """
    document = load_document(JHS_SPEC)
    strip_guidance(document)
    lines = [p.text.strip() for p in document.paragraphs if p.text.strip()]
    return lines or ["WEEKLY LESSON NOTES"]


def build_approved_structure() -> Dict:
    """Canonical approved TemplateStructure IR, DERIVED FROM THE SOURCE DOCX.

    Opens the approved form, strips its authoring guidance and analyzes it, so
    the IR is a live derivative of the golden master rather than a transcribed
    copy. Called on demand (the document is small) so edits to the source flow
    through automatically.
    """
    document = load_document(JHS_SPEC)
    strip_guidance(document)
    structure = analyze_docx_document(document)
    _apply_token_fields(structure)

    structure["meta"] = {
        "title": "",
        "title_lines": _source_paragraph_lines(),
        "paragraph_count": len(document.paragraphs),
        "table_count": len(document.tables),
        "approved_source": SOURCE_DOCUMENT,
        # The GES/NaCCA designation is the source document's own printed title,
        # reproduced verbatim — not an independent SchemeKnit claim.
        "official_ges_claim": True,
        "official_ges_basis": "source document's own printed title",
    }
    structure["detected_family"] = "jhs"
    structure["detected_level"] = "Junior High School"
    structure["sample_paragraphs"] = []
    return structure


# ── Approved lesson JSON schema (AI structured output contract) ──────────────
# Curriculum/metadata fields are deliberately ABSENT: they are deterministic-only
# and must never come from AI. AI may fill activity-family fields only.


class ApprovedPhaseJSON(BaseModel):
    name: str = Field(default="", max_length=120)
    teacher_activities: List[str] = Field(default_factory=list, max_items=20)
    learner_activities: List[str] = Field(default_factory=list, max_items=20)
    resources: List[str] = Field(default_factory=list, max_items=20)

    @field_validator("teacher_activities", "learner_activities", "resources",
                     mode="before")
    @classmethod
    def _coerce_phase_lists(cls, v):
        return _coerce_str_list(v)


def _coerce_str_list(value) -> List[str]:
    """Coerce model-emitted arrays (str | dict | nested) to plain strings.

    Keys stay strict (unknown dropped); item shapes are forgiven. Caps length
    to bound pathological outputs.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value[:500]]
    if not isinstance(value, list):
        return [str(value)[:500]]
    out = []
    for it in value[:30]:
        if isinstance(it, str):
            out.append(it[:500])
        elif isinstance(it, dict):
            for k in ("description", "text", "content", "title", "item", "question"):
                if isinstance(it.get(k), str) and it[k].strip():
                    out.append(it[k].strip()[:500])
                    break
        else:
            out.append(str(it)[:500])
    return [x for x in out if x]


class ApprovedLessonJSON(BaseModel):
    lesson_topic: str = Field(default="", max_length=300)

    @field_validator("core_competencies", "references", "new_words", "assessment",
                     mode="before")
    @classmethod
    def _coerce_lists(cls, v):
        return _coerce_str_list(v)
    performance_indicator: str = Field(default="", max_length=1000)
    core_competencies: List[str] = Field(default_factory=list, max_items=10)
    references: List[str] = Field(default_factory=list, max_items=10)
    new_words: List[str] = Field(default_factory=list, max_items=30)
    phases: List[ApprovedPhaseJSON] = Field(default_factory=list, max_items=5)
    assessment: List[str] = Field(default_factory=list, max_items=20)
    reflection: str = Field(default="", max_length=2000)
    homework: str = Field(default="", max_length=1000)


APPROVED_SYSTEM_PROMPT = """You assist a Ghanaian teacher filling an approved lesson-plan form.
STRICT RULES (from the approved organizational structure only):
1. Return ONLY a flat JSON object matching the approved lesson schema (no markdown fences).
2. Allowed keys ONLY: lesson_topic, performance_indicator, core_competencies,
   references, new_words, phases, assessment, reflection, homework.
3. NEVER invent curriculum facts: no strands, standards, indicators, codes, or dates.
4. phases: use exactly the phase names supplied in the request
   ({starter}, {main}, {plenary}). Do not invent extra phases.
5. Activities go ONLY in phases[].teacher_activities / learner_activities.
6. Resources go ONLY in phases[].resources or references. Assessment items ONLY in
   assessment. Reflection/plenary ONLY in reflection.
7. Keep Ghanaian classroom context with limited resources. No projector/ICT assumptions.
8. Keep each string concise (single paragraph each); arrays hold separate items.
""".format(starter=APPROVED_PHASE_NAMES[0], main=APPROVED_PHASE_NAMES[1],
           plenary=APPROVED_PHASE_NAMES[2])


def validate_approved_lesson_json(data) -> tuple:
    """Validate AI output against the approved schema.

    Returns (ok: bool, normalized dict | error list). Never raises.
    Unknown keys are dropped (strict schema); wrong types coerce-or-fail.
    """
    if not isinstance(data, dict):
        return False, ["payload must be a JSON object"]
    try:
        model = ApprovedLessonJSON(**{k: v for k, v in data.items()
                                      if k in ApprovedLessonJSON.model_fields})
        return True, model.model_dump()
    except ValidationError as e:
        return False, [f"{'.'.join(map(str, err['loc']))}: {err['msg']}"
                       for err in e.errors()]


def normalize_lesson_to_approved(lesson) -> Dict:
    """Build the approved-schema view of a deterministic lesson (no AI needed).

    Curriculum/metadata come from the lesson; activity text from stored fields.
    Missing optional content renders blank — never fabricated.
    """
    def get(name, default=None):
        if isinstance(lesson, dict):
            return lesson.get(name, default)
        return getattr(lesson, name, default)

    def lines(value):
        if not value:
            return []
        if isinstance(value, str):
            return [value]
        out = []
        for it in value:
            if isinstance(it, str):
                out.append(it)
            elif isinstance(it, dict):
                out.append(it.get("description") or it.get("text") or "")
            else:
                out.append(getattr(it, "description", "") or "")
        return [x for x in out if x]

    intro = get("introduction", "") or ""
    main = lines(get("main_activities", []))
    learner = lines(get("learner_activities", []))
    assess = get("assessment", "") or ""
    concl = get("conclusion", "") or ""
    resources = lines(get("teaching_learning_resources", []))
    return {
        "lesson_topic": get("lesson_topic", "") or "",
        "performance_indicator": " ".join(lines(get("learning_objectives", []))),
        "core_competencies": lines(get("core_competencies", [])),
        "references": lines(get("references", [])),
        "new_words": lines(get("keywords", [])),
        "phases": [
            {"name": APPROVED_PHASE_NAMES[0], "teacher_activities": [],
             "learner_activities": [intro] if intro else [], "resources": resources},
            {"name": APPROVED_PHASE_NAMES[1], "teacher_activities": main,
             "learner_activities": learner, "resources": resources},
            {"name": APPROVED_PHASE_NAMES[2], "teacher_activities": [],
             "learner_activities": [], "resources": []},
        ],
        "assessment": [assess] if assess else [],
        "reflection": concl,
        "homework": get("homework", "") or "",
    }

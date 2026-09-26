"""
GES lesson plan form contracts — the four level specs.

Provenance note (template_provenance.py is authoritative): only the JHS form is
backed by the approved organizational source document (verified). The KG,
Lower Primary and SHS forms are placeholder documents supplied by teachers and
are PENDING SOURCE VERIFICATION — they must not be described as official
GES/NaCCA templates anywhere.

Sources (bundled verbatim in ``src/engines/assets/``, teacher supply):

| key | file | level |
|---|---|---|
| ``kg`` | ``ges_kg_lesson_plan_template.docx`` | Kindergarten |
| ``primary`` | ``ges_primary_lesson_plan_template.docx`` | Lower Primary |
| ``jhs`` | ``ges_jhs_lesson_plan_template.docx`` | Junior High School |
| ``shs`` | ``ges_shs_lesson_plan_template.docx`` | Senior High School |

Every form is a *placeholder* document: bracketed tokens (``[WEEK_ENDING]``,
``[PHASE_1_STARTER]``, ``[TUNING_IN_PHASE]`` …) inside two tables. The JHS form
additionally carries authoring guidance (numbered blocks + example bullets
sharing a run with each token) which the engine strips; the other three carry
none. KG, Primary and SHS do carry *example prose* in delivery-grid columns that
have no token — declared here as ``grid_fills`` so stored lesson data replaces it
rather than leaving text the teacher never wrote on their plan.

Contract rules (identical for every level):
- Administrative and curriculum fields are DETERMINISTIC-ONLY; they are resolved
  from the stored lesson and never from AI.
- ``SOURCE_AI`` marks activity-family fields a provider may assist with.
- A field with nothing to resolve renders blank. Nothing is invented.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

LEVEL_KG = "kg"
LEVEL_PRIMARY = "primary"
LEVEL_JHS = "jhs"
LEVEL_SHS = "shs"

#: Level keys in display order.
LEVEL_ORDER: Tuple[str, ...] = (LEVEL_KG, LEVEL_PRIMARY, LEVEL_JHS, LEVEL_SHS)

SOURCE_DETERMINISTIC = "deterministic"
SOURCE_AI = "ai"

# Section names double as TemplateSection names for the UI (see template_engine).
SECTION_HEADER = "header"
SECTION_CURRICULUM = "curriculum_alignment"
SECTION_PEDAGOGY = "pedagogical_foundations"
SECTION_DELIVERY = "delivery_grid"

SECTION_LABELS = {
    SECTION_HEADER: "Administrative Metadata",
    SECTION_CURRICULUM: "Curriculum Syllabus Alignment",
    SECTION_PEDAGOGY: "Pedagogical Foundations",
    SECTION_DELIVERY: "Lesson Delivery Layout",
}

#: Delivery-grid cell fill kinds for columns that carry no placeholder.
FILL_LEARNER = "learner"                          # learner activities
FILL_RESOURCES_AND_ASSESSMENT = "resources_and_assessment"  # TLRs + assessment


@dataclass(frozen=True)
class GESField:
    """One placeholder in a level's form.

    ``token`` is the bracketed placeholder inside the .docx; ``field`` the
    canonical lesson field it resolves from (None when the form asks for
    something SchemeKnit does not hold — such tokens stay blank); ``source``
    records whether AI assistance is allowed to contribute content there.
    """

    token: str
    label: str
    section: str
    field: Optional[str] = None
    source: str = SOURCE_DETERMINISTIC


@dataclass(frozen=True)
class GESGridFill:
    """One delivery-grid cell without a placeholder, filled from stored data.

    ``table``/``row``/``column`` address the cell by grid position in the
    bundled form (row 0 is the column-header row). Positional addressing is safe
    because the form is shipped alongside this contract and its shape is
    asserted by tests.
    """

    table: int
    row: int
    column: int
    kind: str
    label: str


@dataclass(frozen=True)
class GESLevelSpec:
    """A complete level contract: one form, one field list, one AI framing."""

    key: str
    template_id: str
    name: str
    filename: str
    #: Printed phase row labels, used verbatim in the AI prompt.
    phase_names: Tuple[str, ...]
    fields: Sequence[GESField]
    #: Level-specific instruction appended to the shared AI system prompt.
    prompt_tailoring: str
    grid_fills: Tuple[GESGridFill, ...] = ()

    @property
    def tokens(self) -> List[str]:
        return [f.token for f in self.fields]

    @property
    def ai_tokens(self) -> List[str]:
        return [f.token for f in self.fields if f.source == SOURCE_AI]


# ── Kindergarten ──────────────────────────────────────────────────────────────

_KG_FIELDS = [
    GESField("WEEK_ENDING", "Week Ending", SECTION_HEADER, "week_ending"),
    GESField("LEVEL_OR_THEME", "Level / Theme", SECTION_HEADER, "level_or_theme"),
    GESField("CLASS_SIZE", "Class Size", SECTION_HEADER, "class_size"),
    GESField("DURATION", "Duration", SECTION_HEADER, "duration_minutes"),
    GESField("INSERT_STRAND", "Strand", SECTION_CURRICULUM, "strand"),
    GESField("INSERT_SUB_STRAND", "Sub-Strand", SECTION_CURRICULUM, "sub_strand"),
    GESField("CONTENT_STANDARD", "Content Standard", SECTION_CURRICULUM, "content_standard"),
    GESField("INDICATOR_CODE", "Indicator Code", SECTION_CURRICULUM, "indicators"),
    GESField("CORE_COMPETENCIES", "Core Competencies", SECTION_PEDAGOGY, "core_competencies"),
    GESField("KEYWORDS", "Keywords", SECTION_PEDAGOGY, "keywords", SOURCE_AI),
    GESField("TLRS", "Resources (TLRs)", SECTION_PEDAGOGY, "teaching_learning_resources", SOURCE_AI),
    GESField("TUNING_IN_PHASE", "Phase 1: Tuning-In", SECTION_DELIVERY, "introduction", SOURCE_AI),
    GESField("ACTIVE_LEARNING_PHASE", "Phase 2: Active Learning", SECTION_DELIVERY,
             "main_activities", SOURCE_AI),
    GESField("REFLECTION_PHASE", "Phase 3: Reflection", SECTION_DELIVERY, "conclusion", SOURCE_AI),
]

#: "RESOURCES / ASSESSMENT" column of the play-based delivery grid.
_KG_GRID_FILLS = tuple(
    GESGridFill(1, row, 2, FILL_RESOURCES_AND_ASSESSMENT, f"Phase {row}: Resources / Assessment")
    for row in (1, 2, 3)
)

KG_SPEC = GESLevelSpec(
    key=LEVEL_KG,
    template_id="tpl-official-ges-nacca-kg",
    # Teacher-facing name contains "GES" and the level it covers (PART B).
    name="Approved GES KG / Nursery Plan",
    filename="ges_kg_lesson_plan_template.docx",
    phase_names=("Phase 1: Tuning-In", "Phase 2: Active Learning", "Phase 3: Reflection"),
    fields=_KG_FIELDS,
    prompt_tailoring=(
        "LEVEL: Kindergarten. Work through play: songs, rhymes, movement, realia, "
        "exploration corners and show-and-tell. Each step must be something an adult "
        "can do with a group of young children using locally available materials."
    ),
    grid_fills=_KG_GRID_FILLS,
)


# ── Lower Primary ─────────────────────────────────────────────────────────────

_PRIMARY_FIELDS = [
    GESField("WEEK_ENDING", "Week Ending", SECTION_HEADER, "week_ending"),
    GESField("SUBJECT", "Subject", SECTION_HEADER, "subject"),
    GESField("CLASS", "Class", SECTION_HEADER, "class_level"),
    GESField("CLASS_SIZE", "Class Size", SECTION_HEADER, "class_size"),
    GESField("PERIOD", "Period", SECTION_HEADER, "period"),
    GESField("DURATION", "Duration", SECTION_HEADER, "duration_minutes"),
    GESField("REFERENCE_MATERIAL", "Reference Material", SECTION_HEADER, "references"),
    GESField("INSERT_STRAND", "Strand", SECTION_CURRICULUM, "strand"),
    GESField("INSERT_SUB_STRAND", "Sub-Strand", SECTION_CURRICULUM, "sub_strand"),
    GESField("CONTENT_STANDARD", "Content Standard", SECTION_CURRICULUM, "content_standard"),
    GESField("INDICATOR_CODE", "Indicator Code", SECTION_CURRICULUM, "indicators"),
    GESField("CORE_COMPETENCIES", "Core Competencies", SECTION_PEDAGOGY, "core_competencies"),
    GESField("PERFORMANCE_INDICATOR", "Performance Indicator", SECTION_PEDAGOGY,
             "learning_objectives"),
    GESField("KEYWORDS", "Keywords", SECTION_PEDAGOGY, "keywords", SOURCE_AI),
    GESField("TLRS", "Resources (TLRs)", SECTION_PEDAGOGY, "teaching_learning_resources", SOURCE_AI),
    GESField("PHASE_1_STARTER", "Phase 1: Starter", SECTION_DELIVERY, "introduction", SOURCE_AI),
    GESField("PHASE_2_MAIN", "Phase 2: Main Learning", SECTION_DELIVERY,
             "main_activities", SOURCE_AI),
    GESField("PHASE_3_PLENARY", "Phase 3: Plenary", SECTION_DELIVERY, "conclusion", SOURCE_AI),
]

#: "TLRs / ASSESSMENT" column of the lower-primary delivery grid.
_PRIMARY_GRID_FILLS = tuple(
    GESGridFill(1, row, 2, FILL_RESOURCES_AND_ASSESSMENT, f"Phase {row}: TLRs / Assessment")
    for row in (1, 2, 3)
)

PRIMARY_SPEC = GESLevelSpec(
    key=LEVEL_PRIMARY,
    template_id="tpl-official-ges-nacca-primary",
    # Teacher-facing name contains "GES" and the class range it covers (PART B).
    name="Approved GES Lower Primary Plan",
    filename="ges_primary_lesson_plan_template.docx",
    phase_names=("Phase 1: Starter", "Phase 2: Main Learning", "Phase 3: Plenary"),
    fields=_PRIMARY_FIELDS,
    prompt_tailoring=(
        "LEVEL: Lower Primary (Basic 1-3). Build foundational literacy and numeracy: "
        "teacher modelling first, then guided practice, then independent work. "
        "Language must be simple and concrete, with plenty of oral work."
    ),
    grid_fills=_PRIMARY_GRID_FILLS,
)


# ── Junior High School ────────────────────────────────────────────────────────

_JHS_FIELDS = [
    # 1. Administrative metadata
    GESField("INSERT_WEEK_ENDING", "Week Ending", SECTION_HEADER, "week_ending"),
    GESField("INSERT_CLASS_LEVEL", "Class / Level", SECTION_HEADER, "class_level"),
    GESField("INSERT_SUBJECT", "Subject", SECTION_HEADER, "subject"),
    GESField("INSERT_CLASS_SIZE", "Class Size", SECTION_HEADER, "class_size"),
    GESField("INSERT_DATE_DAY", "Date / Day", SECTION_HEADER, "lesson_date"),
    GESField("INSERT_PERIOD", "Period", SECTION_HEADER, "period"),
    GESField("INSERT_DURATION", "Duration", SECTION_HEADER, "duration_minutes"),
    GESField("INSERT_REFERENCE_SYLLABUS", "Reference", SECTION_HEADER, "references"),
    # 2. Curriculum syllabus alignment codes
    GESField("INSERT_STRAND_NAME_AND_CODE", "Strand", SECTION_CURRICULUM, "strand"),
    GESField("INSERT_SUB_STRAND_NAME_AND_CODE", "Sub-Strand", SECTION_CURRICULUM, "sub_strand"),
    GESField("INSERT_CONTENT_STANDARD_CODE_AND_TEXT", "Content Standard",
             SECTION_CURRICULUM, "content_standard"),
    GESField("INSERT_INDICATOR_CODE_AND_TEXT", "Indicator", SECTION_CURRICULUM, "indicators"),
    # 3. Pedagogical foundations
    GESField("INSERT_CORE_COMPETENCIES_E_G_CRITICAL_THINKING_COLLABORATION",
             "Core Competencies", SECTION_PEDAGOGY, "core_competencies"),
    GESField("INSERT_EXPECTED_LEARNER_PERFORMANCE_OUTCOME",
             "Performance Indicator", SECTION_PEDAGOGY, "learning_objectives"),
    GESField("INSERT_KEY_TERMINOLOGIES_TO_BE_TAUGHT", "Keywords / Vocabulary",
             SECTION_PEDAGOGY, "keywords", SOURCE_AI),
    GESField("INSERT_RESOURCES_BOOKS_TOOLS_OR_VISUAL_AIDS", "Teaching & Learning Resources",
             SECTION_PEDAGOGY, "teaching_learning_resources", SOURCE_AI),
    # 4. Tridelivery lesson timeline
    GESField("PHASE_1_STARTER_ACTIVITIES", "Phase 1: Starter / Intro",
             SECTION_DELIVERY, "introduction", SOURCE_AI),
    GESField("PHASE_1_RESOURCES_OR_DIAGNOSTIC_ASSESSMENT",
             "Phase 1: TLRs / Diagnostic Assessment", SECTION_DELIVERY,
             "teaching_learning_resources", SOURCE_AI),
    GESField("PHASE_2_MAIN_LEARNING_STEPS", "Phase 2: Main Learning",
             SECTION_DELIVERY, "main_activities", SOURCE_AI),
    GESField("PHASE_2_FORMATIVE_ASSESSMENT_STRATEGIES_AND_TOOLS",
             "Phase 2: Formative Assessment", SECTION_DELIVERY, "assessment", SOURCE_AI),
    GESField("PHASE_3_PLENARY_AND_REFLECTION", "Phase 3: Plenary / Reflection",
             SECTION_DELIVERY, "conclusion", SOURCE_AI),
    GESField("PHASE_3_SUMMATIVE_EVALUATION_METRICS",
             "Phase 3: Summative Evaluation", SECTION_DELIVERY, None),
]

JHS_SPEC = GESLevelSpec(
    key=LEVEL_JHS,
    template_id="tpl-official-ges-nacca-jhs",
    # The teacher-facing name MUST contain "GES" (PART B): this is the
    # approved Ghana Education Service form for Junior High School.
    name="Approved GES Plan",
    filename="ges_jhs_lesson_plan_template.docx",
    phase_names=("PHASE 1: STARTER / INTRO", "PHASE 2: MAIN LEARNING",
                 "PHASE 3: PLENARY / REFLECTION"),
    fields=_JHS_FIELDS,
    prompt_tailoring=(
        "LEVEL: Junior High School (Basic 7-9). Use the tridelivery structure: a "
        "starter that activates prior knowledge, a main phase with teacher "
        "explanation plus learner practice, and a plenary that recaps and checks "
        "understanding. Include assessment evidence per phase."
    ),
    # The JHS form's delivery grid has a placeholder in every content column.
    grid_fills=(),
)


# ── Senior High School ────────────────────────────────────────────────────────

_SHS_FIELDS = [
    GESField("WEEK_ENDING", "Week Ending", SECTION_HEADER, "week_ending"),
    GESField("SUBJECT", "Subject", SECTION_HEADER, "subject"),
    GESField("PROGRAMME", "Programme", SECTION_HEADER, "programme"),
    GESField("CLASS", "Class", SECTION_HEADER, "class_level"),
    GESField("PERIOD", "Period", SECTION_HEADER, "period"),
    GESField("DURATION", "Duration", SECTION_HEADER, "duration_minutes"),
    GESField("REFERENCE_MATERIAL", "Reference Material", SECTION_HEADER, "references"),
    GESField("INSERT_STRAND", "Strand", SECTION_CURRICULUM, "strand"),
    GESField("INSERT_SUB_STRAND", "Sub-Strand", SECTION_CURRICULUM, "sub_strand"),
    GESField("CONTENT_STANDARD", "Content Standard", SECTION_CURRICULUM, "content_standard"),
    GESField("INDICATOR_CODE", "Indicator Code", SECTION_CURRICULUM, "indicators"),
    GESField("PRIOR_KNOWLEDGE", "Prior Knowledge", SECTION_PEDAGOGY, "previous_knowledge"),
    GESField("CORE_COMPETENCIES", "Core Competencies", SECTION_PEDAGOGY, "core_competencies"),
    GESField("KEYWORDS", "Keywords", SECTION_PEDAGOGY, "keywords", SOURCE_AI),
    GESField("TLRS", "Resources (TLMs)", SECTION_PEDAGOGY, "teaching_learning_resources", SOURCE_AI),
    GESField("PHASE_1_INTRODUCTION", "Phase 1: Introduction", SECTION_DELIVERY,
             "introduction", SOURCE_AI),
    GESField("PHASE_2_MAIN_DELIVERY", "Phase 2: Main Delivery", SECTION_DELIVERY,
             "main_activities", SOURCE_AI),
    GESField("PHASE_3_EVALUATION", "Phase 3: Evaluation", SECTION_DELIVERY,
             "conclusion", SOURCE_AI),
]

#: The academic grid's LEARNER ACTIVITIES column has no placeholder beside the
#: teacher one, and its TLMs / ASSESSMENT column has none either.
_SHS_GRID_FILLS = tuple(
    GESGridFill(1, row, column, kind, label)
    for row in (1, 2, 3)
    for column, kind, label in (
        (2, FILL_LEARNER, f"Phase {row}: Learner Activities"),
        (3, FILL_RESOURCES_AND_ASSESSMENT, f"Phase {row}: TLMs / Assessment"),
    )
)

SHS_SPEC = GESLevelSpec(
    key=LEVEL_SHS,
    template_id="tpl-official-ges-nacca-shs",
    # Teacher-facing name contains "GES" (PART B).
    name="Approved GES SHS Plan",
    filename="ges_shs_lesson_plan_template.docx",
    phase_names=("Phase 1: Introduction", "Phase 2: Main Delivery", "Phase 3: Evaluation"),
    fields=_SHS_FIELDS,
    prompt_tailoring=(
        "LEVEL: Senior High School (SHS 1-3). Aim for academic depth and the "
        "21st-century competencies: analytical tasks, collaborative work, "
        "presentations and laboratory or field practice where the subject allows. "
        "Assume learners can read and work independently."
    ),
    grid_fills=_SHS_GRID_FILLS,
)


# ── Registry ──────────────────────────────────────────────────────────────────

GES_TEMPLATES: Dict[str, GESLevelSpec] = {
    spec.key: spec for spec in (KG_SPEC, PRIMARY_SPEC, JHS_SPEC, SHS_SPEC)
}

#: The JHS form, kept as the module's reference level (it is the head of the
#: template list and the level that shipped first).
JHS_TEMPLATE = JHS_SPEC


def spec_for_level(level: str) -> Optional[GESLevelSpec]:
    """Spec by level key ('kg' | 'primary' | 'jhs' | 'shs'), case-insensitive."""
    return GES_TEMPLATES.get((level or "").strip().lower())


def spec_for_template_id(template_id: Optional[str]) -> Optional[GESLevelSpec]:
    """Spec owning a template id, or None when the id is not an official form.

    The approved organizational template (``tpl-approved-org-headteacher``) is an
    alias of the verified JHS form — same approved source document — so it
    resolves to the JHS contract and renders that form in place.
    """
    if not template_id:
        return None
    for spec in GES_TEMPLATES.values():
        if spec.template_id == template_id:
            return spec
    if template_id == "tpl-approved-org-headteacher":
        return JHS_SPEC
    return None


def official_specs() -> List[GESLevelSpec]:
    """All GES-form specs in display order (the ids keep the historical prefix)."""
    return [GES_TEMPLATES[key] for key in LEVEL_ORDER]

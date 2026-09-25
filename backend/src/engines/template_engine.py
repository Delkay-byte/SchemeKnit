"""
SchemeKnit Template Engine — Milestone 2

Advanced template system with curriculum profiles,
template families, and configurable field schemas.
"""

from typing import List, Optional, Dict, Any
from ..models import (
    Template, TemplateFamily, TemplateSection, TemplateField, TemplateLayout,
    TemplateFieldType, EducationalLevel, ClassLevel, CurriculumProfile,
    CurriculumProfileField, ContentSource,
    CLASS_LEVEL_TO_EDUCATIONAL_LEVEL,
)
from .official_ges_levels import (
    LEVEL_JHS,
    LEVEL_KG,
    LEVEL_PRIMARY,
    LEVEL_SHS,
    SOURCE_AI,
    GESLevelSpec,
    official_specs,
    spec_for_level,
)
from .official_ges_template import (
    TEMPLATE_VERSION as OFFICIAL_GES_TEMPLATE_VERSION,
    sections_for as official_ges_sections,
)
from .wapef_template import (
    TEMPLATE_ID as WAPEF_TEMPLATE_ID,
    TEMPLATE_NAME as WAPEF_TEMPLATE_NAME,
    TEMPLATE_VERSION as WAPEF_TEMPLATE_VERSION,
    WAPEF_TOKEN_FIELDS,
)
from .template_provenance import provenance_for_template


# ── Curriculum Profiles ──────────────────────────────────────────────────────

JHS_PROFILE = CurriculumProfile(
    name="JHS Profile",
    educational_level=EducationalLevel.JHS,
    description="Junior High School lesson plan profile",
    supported_class_levels=[ClassLevel.BASIC_7, ClassLevel.BASIC_8, ClassLevel.BASIC_9],
    lesson_plan_fields=[
        CurriculumProfileField(name="strand", label="Strand", field_type="text", required=True, order=1),
        CurriculumProfileField(name="sub_strand", label="Sub-Strand", field_type="text", required=True, order=2),
        CurriculumProfileField(name="content_standard", label="Content Standard", field_type="textarea", required=True, order=3),
        CurriculumProfileField(name="indicators", label="Indicators", field_type="textarea", required=True, order=4),
        CurriculumProfileField(name="learning_objectives", label="Learning Objectives", field_type="textarea", required=True, order=5),
        CurriculumProfileField(name="core_competencies", label="Core Competencies", field_type="text", order=6),
        CurriculumProfileField(name="previous_knowledge", label="Previous Knowledge", field_type="textarea", order=7),
        CurriculumProfileField(name="teaching_learning_resources", label="Resources", field_type="textarea", order=8),
        CurriculumProfileField(name="introduction", label="Introduction", field_type="textarea", required=True, order=9),
        CurriculumProfileField(name="main_activities", label="Main Activities", field_type="textarea", required=True, order=10),
        CurriculumProfileField(name="learner_activities", label="Learner Activities", field_type="textarea", required=True, order=11),
        CurriculumProfileField(name="teacher_activities", label="Teacher Activities", field_type="textarea", required=True, order=12),
        CurriculumProfileField(name="assessment", label="Assessment", field_type="textarea", required=True, order=13),
        CurriculumProfileField(name="conclusion", label="Conclusion", field_type="textarea", order=14),
        CurriculumProfileField(name="reflection", label="Reflection", field_type="textarea", order=15),
    ],
    template_family="jhs",
    generation_rules={"lessons_per_week": 3, "duration_minutes": 60},
)

PRIMARY_PROFILE = CurriculumProfile(
    name="Primary Profile",
    educational_level=EducationalLevel.PRIMARY,
    description="Primary school lesson plan profile",
    supported_class_levels=[ClassLevel.BASIC_1, ClassLevel.BASIC_2, ClassLevel.BASIC_3,
                            ClassLevel.BASIC_4, ClassLevel.BASIC_5, ClassLevel.BASIC_6],
    lesson_plan_fields=[
        CurriculumProfileField(name="strand", label="Strand", field_type="text", required=True, order=1),
        CurriculumProfileField(name="sub_strand", label="Sub-Strand", field_type="text", required=True, order=2),
        CurriculumProfileField(name="content_standard", label="Content Standard", field_type="textarea", required=True, order=3),
        CurriculumProfileField(name="indicators", label="Indicators", field_type="textarea", required=True, order=4),
        CurriculumProfileField(name="learning_objectives", label="Learning Objectives", field_type="textarea", required=True, order=5),
        CurriculumProfileField(name="previous_knowledge", label="Previous Knowledge", field_type="textarea", order=6),
        CurriculumProfileField(name="teaching_learning_resources", label="Resources", field_type="textarea", order=7),
        CurriculumProfileField(name="introduction", label="Introduction", field_type="textarea", required=True, order=8),
        CurriculumProfileField(name="main_activities", label="Main Activities", field_type="textarea", required=True, order=9),
        CurriculumProfileField(name="learner_activities", label="Learner Activities", field_type="textarea", required=True, order=10),
        CurriculumProfileField(name="assessment", label="Assessment", field_type="textarea", required=True, order=11),
        CurriculumProfileField(name="conclusion", label="Conclusion/Recap", field_type="textarea", order=12),
    ],
    template_family="primary",
    generation_rules={"lessons_per_week": 3, "duration_minutes": 35},
)

EARLY_CHILDHOOD_PROFILE = CurriculumProfile(
    name="Early Childhood Profile",
    educational_level=EducationalLevel.EARLY_CHILDHOOD,
    description="Nursery and KG lesson plan profile",
    supported_class_levels=[ClassLevel.NURSERY, ClassLevel.KG1, ClassLevel.KG2],
    lesson_plan_fields=[
        CurriculumProfileField(name="strand", label="Theme/Area", field_type="text", required=True, order=1),
        CurriculumProfileField(name="sub_strand", label="Topic", field_type="text", required=True, order=2),
        CurriculumProfileField(name="learning_objectives", label="Learning Objectives", field_type="textarea", required=True, order=3),
        CurriculumProfileField(name="teaching_learning_resources", label="Resources", field_type="textarea", order=4),
        CurriculumProfileField(name="introduction", label="Introduction/Arrival", field_type="textarea", required=True, order=5),
        CurriculumProfileField(name="main_activities", label="Main Activity", field_type="textarea", required=True, order=6),
        CurriculumProfileField(name="learner_activities", label="Learner Activity", field_type="textarea", required=True, order=7),
        CurriculumProfileField(name="assessment", label="Observation/Assessment", field_type="textarea", required=True, order=8),
        CurriculumProfileField(name="conclusion", label="Wrap-up/Song", field_type="textarea", order=9),
    ],
    template_family="early_childhood",
    generation_rules={"lessons_per_week": 5, "duration_minutes": 30},
)

SHS_PROFILE = CurriculumProfile(
    name="SHS Profile",
    educational_level=EducationalLevel.SHS,
    description="Senior High School lesson plan profile",
    supported_class_levels=[ClassLevel.SHS_1, ClassLevel.SHS_2, ClassLevel.SHS_3],
    lesson_plan_fields=[
        CurriculumProfileField(name="strand", label="Strand", field_type="text", required=True, order=1),
        CurriculumProfileField(name="sub_strand", label="Sub-Strand", field_type="text", required=True, order=2),
        CurriculumProfileField(name="content_standard", label="Content Standard", field_type="textarea", required=True, order=3),
        CurriculumProfileField(name="indicators", label="Indicators", field_type="textarea", required=True, order=4),
        CurriculumProfileField(name="essential_questions", label="Essential Questions", field_type="textarea", order=5),
        CurriculumProfileField(name="learning_objectives", label="Learning Objectives", field_type="textarea", required=True, order=6),
        CurriculumProfileField(name="core_competencies", label="Core Competencies", field_type="text", order=7),
        CurriculumProfileField(name="keywords", label="Keywords", field_type="text", order=8),
        CurriculumProfileField(name="previous_knowledge", label="Previous Knowledge", field_type="textarea", order=9),
        CurriculumProfileField(name="teaching_learning_resources", label="Resources", field_type="textarea", order=10),
        CurriculumProfileField(name="introduction", label="Introduction", field_type="textarea", required=True, order=11),
        CurriculumProfileField(name="main_activities", label="Main Activities", field_type="textarea", required=True, order=12),
        CurriculumProfileField(name="learner_activities", label="Learner Activities", field_type="textarea", required=True, order=13),
        CurriculumProfileField(name="teacher_activities", label="Teacher Activities", field_type="textarea", required=True, order=14),
        CurriculumProfileField(name="differentiation", label="Differentiation", field_type="textarea", order=15),
        CurriculumProfileField(name="assessment", label="Assessment", field_type="textarea", required=True, order=16),
        CurriculumProfileField(name="homework", label="Homework/Follow-up", field_type="textarea", order=17),
        CurriculumProfileField(name="conclusion", label="Conclusion", field_type="textarea", order=18),
        CurriculumProfileField(name="reflection", label="Reflection", field_type="textarea", order=19),
    ],
    template_family="shs",
    generation_rules={"lessons_per_week": 3, "duration_minutes": 80},
)

ALL_PROFILES = [EARLY_CHILDHOOD_PROFILE, PRIMARY_PROFILE, JHS_PROFILE, SHS_PROFILE]
PROFILE_MAP = {p.educational_level: p for p in ALL_PROFILES}


def get_profile_for_class_level(class_level: ClassLevel) -> CurriculumProfile:
    el = CLASS_LEVEL_TO_EDUCATIONAL_LEVEL.get(class_level, EducationalLevel.JHS)
    return PROFILE_MAP.get(el, JHS_PROFILE)


# ── Template Definitions ──────────────────────────────────────────────────────

def _make_jhs_sections() -> List[TemplateSection]:
    return [
        TemplateSection(name="header", label="Lesson Plan Header", order=0, fields=[
            TemplateField(name="school_name", label="School", field_type=TemplateFieldType.TEXT, order=0),
            TemplateField(name="teacher_name", label="Teacher", field_type=TemplateFieldType.TEXT, order=1),
            TemplateField(name="subject", label="Subject", field_type=TemplateFieldType.TEXT, order=2),
            TemplateField(name="class_level", label="Class", field_type=TemplateFieldType.TEXT, order=3),
            TemplateField(name="class_size", label="Class Size", field_type=TemplateFieldType.NUMBER, order=4),
            TemplateField(name="lesson_date", label="Date", field_type=TemplateFieldType.DATE, order=5),
            TemplateField(name="duration_minutes", label="Duration", field_type=TemplateFieldType.NUMBER, order=6),
        ]),
        TemplateSection(name="strand_info", label="Strand / Sub-Strand", order=1, fields=[
            TemplateField(name="strand", label="Strand", field_type=TemplateFieldType.TEXT, required=True, order=0),
            TemplateField(name="sub_strand", label="Sub-Strand", field_type=TemplateFieldType.TEXT, required=True, order=1),
        ]),
        TemplateSection(name="content_standard", label="Content Standard", order=2, fields=[
            TemplateField(name="content_standard_code", label="Code", field_type=TemplateFieldType.TEXT, order=0),
            TemplateField(name="content_standard", label="Description", field_type=TemplateFieldType.TEXTAREA, required=True, order=1),
        ]),
        TemplateSection(name="indicators", label="Indicators", order=3, fields=[
            TemplateField(name="indicators", label="Indicators", field_type=TemplateFieldType.TEXTAREA, required=True, order=0),
        ]),
        TemplateSection(name="objectives", label="Learning Objectives", order=4, fields=[
            TemplateField(name="learning_objectives", label="Objectives", field_type=TemplateFieldType.TEXTAREA, required=True, order=0),
        ]),
        TemplateSection(name="resources", label="Teaching & Learning Resources", order=5, fields=[
            TemplateField(name="teaching_learning_resources", label="Resources", field_type=TemplateFieldType.TEXTAREA, order=0),
        ]),
        TemplateSection(name="introduction", label="Introduction / Starter", order=6, fields=[
            TemplateField(name="introduction", label="Introduction", field_type=TemplateFieldType.TEXTAREA, required=True, order=0),
        ]),
        TemplateSection(name="main_activities", label="Main Teaching Activities", order=7, fields=[
            TemplateField(name="main_activities", label="Activities", field_type=TemplateFieldType.TEXTAREA, required=True, order=0),
        ]),
        TemplateSection(name="learner_activities", label="Learner Activities", order=8, fields=[
            TemplateField(name="learner_activities", label="Activities", field_type=TemplateFieldType.TEXTAREA, required=True, order=0),
        ]),
        TemplateSection(name="teacher_activities", label="Teacher Activities", order=9, fields=[
            TemplateField(name="teacher_activities", label="Activities", field_type=TemplateFieldType.TEXTAREA, required=True, order=0),
        ]),
        TemplateSection(name="assessment", label="Assessment", order=10, fields=[
            TemplateField(name="assessment", label="Assessment", field_type=TemplateFieldType.TEXTAREA, required=True, order=0),
        ]),
        TemplateSection(name="conclusion", label="Conclusion / Reflection", order=11, fields=[
            TemplateField(name="conclusion", label="Conclusion", field_type=TemplateFieldType.TEXTAREA, order=0),
            TemplateField(name="reflection", label="Reflection", field_type=TemplateFieldType.TEXTAREA, order=1),
        ]),
    ]


def _make_approved_sections() -> List[TemplateSection]:
    """Sections derived from the canonical approved organizational structure.

    The structure is generated from the approved source document itself (see
    ``approved_template.build_approved_structure``), so the field list shown in
    the UI tracks the source rather than a transcription.
    """
    from .approved_template import build_approved_structure
    struct = build_approved_structure()
    sections = []
    for i, m in enumerate(struct["mappings"]):
        ftype = TemplateFieldType.DATE if m["field"] == "lesson_date" else (
            TemplateFieldType.NUMBER if m["field"] in ("class_size", "lesson_number",
                                                       "week_number", "duration_minutes")
            else TemplateFieldType.TEXTAREA)
        sections.append(TemplateSection(
            name=f"approved_{i}", label=m["label"], order=i,
            fields=[TemplateField(name=m["field"] or m["label"], label=m["label"],
                                  field_type=ftype, required=False)],
        ))
    return sections


def _make_wapef_sections() -> List[TemplateSection]:
    """Sections for the Approved WAPEF Plan, derived from the form's token
    contract (same document the renderer fills in place).

    The four WAPEF structured fields are SELECT fields bound to their approved
    option lists (``wapef_fields``); the teacher picks them in review and they
    are never AI-generated.
    """
    from .wapef_fields import (
        WAPEF_DEEP_HOPES, WAPEF_GODS_STORY, WAPEF_STORYLINES,
        WAPEF_THROUGH_LINES,
    )

    field_type_by_token = {
        "WEEK": TemplateFieldType.NUMBER,
        "CLASS_SIZE": TemplateFieldType.NUMBER,
    }
    token_groups = [
        ("wapef_metadata", "Lesson Metadata", (
            "WEEK", "WEEK_ENDING", "SUBJECT", "CLASS", "CLASS_SIZE",
        )),
        ("wapef_curriculum", "Curriculum Alignment", (
            "STRAND", "SUB_STRAND", "CONTENT_STANDARD", "LEARNING_INDICATOR",
            "PERFORMANCE_INDICATOR", "CORE_COMPETENCIES", "KEY_WORDS",
        )),
        ("wapef_special", "WAPEF Special Fields", (
            "THROUGH_LINE", "GODS_STORY", "DEEP_HOPE", "STORYLINE",
        )),
        ("wapef_delivery", "Lesson Delivery", (
            "PHASE_1_STARTER", "PHASE_1_RESOURCES", "PHASE_2_MAIN",
            "PHASE_2_RESOURCES", "PHASE_3_PLENARY", "PHASE_3_RESOURCES",
            "EVALUATION", "REMARKS",
        )),
    ]
    options_by_token = {
        "THROUGH_LINE": WAPEF_THROUGH_LINES,
        "GODS_STORY": WAPEF_GODS_STORY,
        "DEEP_HOPE": WAPEF_DEEP_HOPES,
        "STORYLINE": WAPEF_STORYLINES,
    }
    label_overrides = {
        "THROUGH_LINE": "Through line",
        "GODS_STORY": "God's Story",
        "LEARNING_INDICATOR": "Learning Indicator",
    }
    sections: List[TemplateSection] = []
    for order, (name, label, tokens) in enumerate(token_groups):
        fields = []
        for index, token in enumerate(tokens):
            base = token.lower()
            field_name = ("wapef_" + base.replace("_", " ").strip()
                          .replace(" ", "_"))
            if token == "THROUGH_LINE":
                field_name = "wapef_through_lines"
            elif token == "GODS_STORY":
                field_name = "wapef_gods_story"
            elif token == "DEEP_HOPE":
                field_name = "wapef_deep_hope"
            elif token == "STORYLINE":
                field_name = "wapef_storyline"
            elif token == "WEEK_ENDING":
                field_name = "week_ending"
            elif token == "SUBJECT":
                field_name = "subject"
            elif token == "CLASS":
                field_name = "class_level"
            elif token == "CLASS_SIZE":
                field_name = "class_size"
            elif token == "STRAND":
                field_name = "strand"
            elif token == "SUB_STRAND":
                field_name = "sub_strand"
            elif token == "CONTENT_STANDARD":
                field_name = "content_standard"
            elif token == "LEARNING_INDICATOR":
                field_name = "indicators"
            elif token == "PERFORMANCE_INDICATOR":
                field_name = "learning_objectives"
            elif token == "CORE_COMPETENCIES":
                field_name = "core_competencies"
            elif token == "KEY_WORDS":
                field_name = "keywords"
            elif token == "PHASE_1_STARTER":
                field_name = "introduction"
            elif token == "PHASE_2_MAIN":
                field_name = "main_activities"
            elif token == "PHASE_3_PLENARY":
                field_name = "conclusion"
            elif token == "EVALUATION":
                field_name = "assessment"
            elif token == "PHASE_1_RESOURCES":
                field_name = "teaching_learning_resources"
            elif token == "PHASE_2_RESOURCES":
                field_name = "teaching_learning_resources"
            elif token == "PHASE_3_RESOURCES":
                field_name = "teaching_learning_resources"
            elif token == "REMARKS":
                field_name = "remarks"
            options = options_by_token.get(token)
            fields.append(TemplateField(
                name=field_name,
                label=label_overrides.get(
                    token, token.replace("_", " ").title()),
                field_type=(TemplateFieldType.SELECT if options
                            else field_type_by_token.get(token,
                                                         TemplateFieldType.TEXTAREA)),
                order=index,
                options=list(options) if options else [],
                source=(ContentSource.DETERMINISTIC if token not in
                        ("PHASE_1_STARTER", "PHASE_2_MAIN", "PHASE_3_PLENARY")
                        else ContentSource.AI),
            ))
        sections.append(TemplateSection(
            name=name, label=label, order=order, fields=fields))
    return sections


def _make_early_childhood_sections() -> List[TemplateSection]:
    return [
        TemplateSection(name="header", label="Lesson Plan Header", order=0, fields=[
            TemplateField(name="school_name", label="School", field_type=TemplateFieldType.TEXT, order=0),
            TemplateField(name="teacher_name", label="Teacher", field_type=TemplateFieldType.TEXT, order=1),
            TemplateField(name="class_level", label="Class", field_type=TemplateFieldType.TEXT, order=2),
            TemplateField(name="lesson_date", label="Date", field_type=TemplateFieldType.DATE, order=3),
            TemplateField(name="duration_minutes", label="Duration (min)", field_type=TemplateFieldType.NUMBER, order=4),
        ]),
        TemplateSection(name="topic", label="Theme / Topic", order=1, fields=[
            TemplateField(name="strand", label="Theme/Area", field_type=TemplateFieldType.TEXT, required=True, order=0),
            TemplateField(name="sub_strand", label="Topic", field_type=TemplateFieldType.TEXT, required=True, order=1),
        ]),
        TemplateSection(name="objectives", label="Learning Objectives", order=2, fields=[
            TemplateField(name="learning_objectives", label="Objectives", field_type=TemplateFieldType.TEXTAREA, required=True, order=0),
        ]),
        TemplateSection(name="resources", label="Resources", order=3, fields=[
            TemplateField(name="teaching_learning_resources", label="Resources", field_type=TemplateFieldType.TEXTAREA, order=0),
        ]),
        TemplateSection(name="introduction", label="Introduction / Arrival Activity", order=4, fields=[
            TemplateField(name="introduction", label="Activity", field_type=TemplateFieldType.TEXTAREA, required=True, order=0),
        ]),
        TemplateSection(name="main_activities", label="Main Activity", order=5, fields=[
            TemplateField(name="main_activities", label="Activity", field_type=TemplateFieldType.TEXTAREA, required=True, order=0),
        ]),
        TemplateSection(name="learner_activities", label="Learner Activity", order=6, fields=[
            TemplateField(name="learner_activities", label="Activity", field_type=TemplateFieldType.TEXTAREA, required=True, order=0),
        ]),
        TemplateSection(name="assessment", label="Observation / Assessment", order=7, fields=[
            TemplateField(name="assessment", label="Assessment", field_type=TemplateFieldType.TEXTAREA, required=True, order=0),
        ]),
        TemplateSection(name="conclusion", label="Wrap-up / Song / Story", order=8, fields=[
            TemplateField(name="conclusion", label="Wrap-up", field_type=TemplateFieldType.TEXTAREA, order=0),
        ]),
    ]


def _make_primary_sections() -> List[TemplateSection]:
    return [
        TemplateSection(name="header", label="Lesson Plan Header", order=0, fields=[
            TemplateField(name="school_name", label="School", field_type=TemplateFieldType.TEXT, order=0),
            TemplateField(name="teacher_name", label="Teacher", field_type=TemplateFieldType.TEXT, order=1),
            TemplateField(name="subject", label="Subject", field_type=TemplateFieldType.TEXT, order=2),
            TemplateField(name="class_level", label="Class", field_type=TemplateFieldType.TEXT, order=3),
            TemplateField(name="lesson_date", label="Date", field_type=TemplateFieldType.DATE, order=4),
            TemplateField(name="duration_minutes", label="Duration (min)", field_type=TemplateFieldType.NUMBER, order=5),
        ]),
        TemplateSection(name="strand_info", label="Strand / Sub-Strand", order=1, fields=[
            TemplateField(name="strand", label="Strand", field_type=TemplateFieldType.TEXT, required=True, order=0),
            TemplateField(name="sub_strand", label="Sub-Strand", field_type=TemplateFieldType.TEXT, required=True, order=1),
        ]),
        TemplateSection(name="content_standard", label="Content Standard", order=2, fields=[
            TemplateField(name="content_standard", label="Standard", field_type=TemplateFieldType.TEXTAREA, required=True, order=0),
        ]),
        TemplateSection(name="indicators", label="Indicators", order=3, fields=[
            TemplateField(name="indicators", label="Indicators", field_type=TemplateFieldType.TEXTAREA, required=True, order=0),
        ]),
        TemplateSection(name="objectives", label="Learning Objectives", order=4, fields=[
            TemplateField(name="learning_objectives", label="Objectives", field_type=TemplateFieldType.TEXTAREA, required=True, order=0),
        ]),
        TemplateSection(name="resources", label="Resources", order=5, fields=[
            TemplateField(name="teaching_learning_resources", label="Resources", field_type=TemplateFieldType.TEXTAREA, order=0),
        ]),
        TemplateSection(name="introduction", label="Introduction", order=6, fields=[
            TemplateField(name="introduction", label="Introduction", field_type=TemplateFieldType.TEXTAREA, required=True, order=0),
        ]),
        TemplateSection(name="main_activities", label="Main Activities", order=7, fields=[
            TemplateField(name="main_activities", label="Activities", field_type=TemplateFieldType.TEXTAREA, required=True, order=0),
        ]),
        TemplateSection(name="learner_activities", label="Learner Activities", order=8, fields=[
            TemplateField(name="learner_activities", label="Activities", field_type=TemplateFieldType.TEXTAREA, required=True, order=0),
        ]),
        TemplateSection(name="assessment", label="Assessment", order=9, fields=[
            TemplateField(name="assessment", label="Assessment", field_type=TemplateFieldType.TEXTAREA, required=True, order=0),
        ]),
        TemplateSection(name="conclusion", label="Conclusion / Recap", order=10, fields=[
            TemplateField(name="conclusion", label="Conclusion", field_type=TemplateFieldType.TEXTAREA, order=0),
        ]),
    ]


#: Family and educational level for each GES-form level.
OFFICIAL_GES_LEVELS = {
    LEVEL_KG: (TemplateFamily.EARLY_CHILDHOOD, EducationalLevel.EARLY_CHILDHOOD),
    LEVEL_PRIMARY: (TemplateFamily.PRIMARY, EducationalLevel.PRIMARY),
    LEVEL_JHS: (TemplateFamily.JHS, EducationalLevel.JHS),
    LEVEL_SHS: (TemplateFamily.SHS, EducationalLevel.SHS),
}

#: Levels whose official form covers every class level in its family, so it is
#: simply that family's default.
OFFICIAL_GES_WHOLE_LEVEL = (LEVEL_KG, LEVEL_JHS, LEVEL_SHS)

#: The GES primary form is labelled LOWER PRIMARY: it is the primary default for
#: Basic 1-3 only. Basic 4-6 keeps the standard primary template until an
#: upper-primary GES form is supplied (see docs/OFFICIAL_GES_TEMPLATE.md).
OFFICIAL_GES_LOWER_PRIMARY_CLASSES = (ClassLevel.BASIC_1, ClassLevel.BASIC_2,
                                     ClassLevel.BASIC_3)

#: Descriptions state provenance honestly: the JHS form is the approved
#: organizational source document; KG, Lower Primary and SHS are placeholder
#: forms awaiting source verification (see template_provenance.py).
_OFFICIAL_GES_DESCRIPTIONS = {
    LEVEL_KG: "GES-style Kindergarten form with the play-based delivery grid "
              "(Tuning-In, Active Learning, Reflection). PENDING SOURCE VERIFICATION: "
              "no approved organizational source has confirmed this layout.",
    LEVEL_PRIMARY: "GES-style Lower Primary form (Basic 1-3): foundational skills, "
                   "teacher modelling and a Starter / Main / Plenary grid. PENDING "
                   "SOURCE VERIFICATION.",
    LEVEL_JHS: "Approved Organizational Lesson Plan (verified headteacher source): "
               "administrative metadata, curriculum syllabus alignment codes, "
               "pedagogical foundations and the tridelivery lesson timeline.",
    LEVEL_SHS: "GES-style Senior High School form: programme and prior knowledge "
               "fields with the CCP academic delivery grid. PENDING SOURCE "
               "VERIFICATION.",
}

_OFFICIAL_GES_FEATURES = {
    LEVEL_KG: ["Play-based delivery grid", "Tuning-In / Active Learning / Reflection",
               "Pending source verification"],
    LEVEL_PRIMARY: ["Lower Primary (Basic 1-3)", "Starter / Main Learning / Plenary",
                    "Pending source verification"],
    LEVEL_JHS: ["Approved organizational source", "Tridelivery lesson timeline",
                "Curriculum alignment codes"],
    LEVEL_SHS: ["CCP academic delivery grid", "Prior knowledge and programme fields",
                "Pending source verification"],
}


def _make_official_ges_sections(spec: GESLevelSpec) -> List[TemplateSection]:
    """Sections for one official GES/NaCCA placeholder form.

    Derived from the level contract in ``official_ges_levels``: the bundled .docx
    is filled by its own renderer (bracketed placeholders rather than the section
    renderers), so these sections describe the form to the UI while
    ``placeholder`` records the exact token each field fills.
    """
    date_fields = {"lesson_date", "week_ending"}
    number_fields = {"class_size", "duration_minutes"}
    sections: List[TemplateSection] = []
    for order, (name, label, fields) in enumerate(official_ges_sections(spec)):
        sections.append(TemplateSection(
            name=name, label=label, order=order,
            fields=[
                TemplateField(
                    name=field.field or field.token,
                    label=field.label,
                    field_type=(TemplateFieldType.DATE if field.field in date_fields
                                else TemplateFieldType.NUMBER if field.field in number_fields
                                else TemplateFieldType.TEXTAREA),
                    order=index,
                    placeholder=field.token,
                    source=(ContentSource.AI if field.source == SOURCE_AI
                            else ContentSource.DETERMINISTIC),
                )
                for index, field in enumerate(fields)
            ],
        ))
    return sections


def _official_ges_template(spec: GESLevelSpec) -> Template:
    """Build the built-in Template entry for one GES-style placeholder form.

    ``is_official`` comes from the provenance registry, never asserted here:
    every bundled GES/NaCCA form is verified against its own source document.
    ``is_default`` marks the verified form that is the teacher-facing default
    for its level — including Primary, whose GES form is the only approved
    primary template and so defaults the whole level (Basic 1-6).
    """
    family, level = OFFICIAL_GES_LEVELS[spec.key]
    provenance = provenance_for_template(spec.template_id)
    return Template(
        id=spec.template_id,
        name=spec.name,
        family=family,
        educational_level=level,
        description=_OFFICIAL_GES_DESCRIPTIONS[spec.key],
        features=_OFFICIAL_GES_FEATURES[spec.key],
        sections=_make_official_ges_sections(spec),
        is_default=True,
        is_official=provenance.official,
        version=OFFICIAL_GES_TEMPLATE_VERSION,
        author=("Approved organizational source via SchemeKnit" if provenance.official
                else "Teacher supply (pending source verification)"),
    )


DEFAULT_TEMPLATES: List[Template] = [

    # The four GES-style forms come first, so each is its own level's default.
    # Only the JHS form is verified-approved; the rest carry pending provenance
    # (see template_provenance.py). JHS heads the list because get_template_by_type
    # returns the head of it: that is the historical generic fallback, and every
    # level-aware caller resolves its own form (see docx_export.default_template_for_lessons).
    _official_ges_template(spec_for_level(LEVEL_JHS)),
    *[_official_ges_template(spec) for spec in official_specs()
      if spec.key != LEVEL_JHS],
    Template(
        id="tpl-jhs-ges",
        name="GES-Style (JHS)",
        family=TemplateFamily.JHS,
        educational_level=EducationalLevel.JHS,
        description="Standard Ghana Education Service lesson plan format for JHS",
        features=["Full curriculum mapping", "Strand/sub-strand structure", "Core competencies"],
        sections=_make_jhs_sections(),
        is_default=False,
        is_official=False,
        author="SchemeKnit",
    ),
    Template(
        id="tpl-jhs-professional",
        name="Professional (JHS)",
        family=TemplateFamily.JHS,
        educational_level=EducationalLevel.JHS,
        description="Clean professional format for JHS",
        features=["Clean layout", "Compact design"],
        sections=_make_jhs_sections(),
        is_official=False,
        author="SchemeKnit",
    ),
    Template(
        id="tpl-primary-standard",
        name="Standard (Primary)",
        family=TemplateFamily.PRIMARY,
        educational_level=EducationalLevel.PRIMARY,
        description="Standard lesson plan format for Primary schools",
        features=["Age-appropriate structure", "Simplified curriculum mapping"],
        sections=_make_primary_sections(),
        # The verified GES primary form is the teacher-facing default for the
        # whole Primary level (Basic 1-3 directly; Basic 4-6 falls back to it so
        # a teacher's default is always an approved template). This legacy
        # SchemeKnit-standard form is hidden from the teacher selection.
        is_default=False,
        is_official=False,
        author="SchemeKnit",
    ),
    Template(
        id="tpl-ec-activity",
        name="Activity-Based (KG)",
        family=TemplateFamily.EARLY_CHILDHOOD,
        educational_level=EducationalLevel.EARLY_CHILDHOOD,
        description="Activity-based lesson plan for Nursery and KG",
        features=["Play-based learning", "Observation-focused assessment"],
        sections=_make_early_childhood_sections(),
        is_default=False,
        is_official=False,
        author="SchemeKnit",
    ),
    Template(
        id="tpl-shs-ges",
        name="GES-Style (SHS)",
        family=TemplateFamily.SHS,
        educational_level=EducationalLevel.SHS,
        description="Standard Ghana Education Service lesson plan format for SHS",
        features=["Full curriculum mapping", "Essential questions", "Differentiation"],
        sections=_make_jhs_sections(),
        is_default=False,
        is_official=False,
        author="SchemeKnit",
    ),
    Template(
        id=WAPEF_TEMPLATE_ID,
        name=WAPEF_TEMPLATE_NAME,
        family=TemplateFamily.EARLY_CHILDHOOD,
        educational_level=EducationalLevel.EARLY_CHILDHOOD,
        description="The approved WAPEF lesson-plan structure (metadata table, "
                    "three-phase delivery grid, evaluation and remarks), rendered "
                    "from the supplied WAPEF source document itself so the output "
                    "matches it by construction. One common plan for Nursery, KG, "
                    "Basic and JHS. Deep Hope, Storyline, Through lines and "
                    "God's Story are teacher-selected structured fields.",
        features=["Approved WAPEF source", "Teacher-selected WAPEF fields",
                  "One plan for Nursery-KG-JHS", "Verified against source"],
        sections=_make_wapef_sections(),
        is_default=False,
        is_official=True,
        version=WAPEF_TEMPLATE_VERSION,
        author="Approved WAPEF source via SchemeKnit",
    ),
    Template(
        id="tpl-approved-org-headteacher",
        name="Approved Organizational Lesson Plan (Headteacher Source)",
        family=TemplateFamily.JHS,
        educational_level=EducationalLevel.JHS,
        description="Approved organizational weekly lesson plan supplied by the "
                    "headteacher: administrative metadata, curriculum syllabus "
                    "alignment, pedagogical foundations and the tridelivery "
                    "timeline. Rendered from the verified approved source document "
                    "itself, so the output matches its table topology exactly "
                    "(see template_provenance.py).",
        features=["Approved organizational source", "Tridelivery lesson timeline",
                  "Curriculum alignment codes", "Verified against source"],
        sections=_make_approved_sections(),
        is_default=False,
        is_official=True,
        version="1.0",
        author="Approved organizational source via SchemeKnit",
    ),
]


def get_template_by_id(template_id: str) -> Optional[Template]:
    for t in DEFAULT_TEMPLATES:
        if t.id == template_id:
            return t
    return None


def get_templates_for_level(educational_level: EducationalLevel) -> List[Template]:
    return [t for t in DEFAULT_TEMPLATES if t.educational_level == educational_level]


def get_templates_for_class_level(class_level: ClassLevel) -> List[Template]:
    el = CLASS_LEVEL_TO_EDUCATIONAL_LEVEL.get(class_level, EducationalLevel.JHS)
    return get_templates_for_level(el)


def get_default_template_for_level(educational_level: EducationalLevel) -> Template:
    templates = get_templates_for_level(educational_level)
    for t in templates:
        if t.is_default:
            return t
    return templates[0] if templates else DEFAULT_TEMPLATES[0]


def get_default_template_for_class_level(class_level: ClassLevel) -> Template:
    """The default template for one class level.

    Educational-level defaults are enough for KG, JHS and SHS, whose official
    forms cover every class in the family. Primary is the exception: the GES
    form is a LOWER PRIMARY form. Basic 1-3 gets it directly. Basic 4-6 (Upper
    Primary) has no separately verified form, so it falls back to the same
    verified primary form rather than to a non-approved SchemeKnit-standard
    template — a teacher's default selection is always an approved form.
    """
    official = get_template_by_id(spec_for_level(LEVEL_PRIMARY).template_id)
    if class_level in OFFICIAL_GES_LOWER_PRIMARY_CLASSES or (
            CLASS_LEVEL_TO_EDUCATIONAL_LEVEL.get(class_level) == EducationalLevel.PRIMARY
            and official is not None):
        if official is not None:
            return official
    el = CLASS_LEVEL_TO_EDUCATIONAL_LEVEL.get(class_level, EducationalLevel.JHS)
    return get_default_template_for_level(el)


def get_visible_sections(template: Template) -> List[TemplateSection]:
    return sorted([s for s in template.sections if s.visible], key=lambda s: s.order)


def get_section_by_name(template: Template, name: str) -> Optional[TemplateSection]:
    for s in template.sections:
        if s.name == name:
            return s
    return None


def get_template_by_type(template_type) -> Template:
    """Backward-compatible: returns the head of DEFAULT_TEMPLATES.

    That is now the official GES/NaCCA form, so exports that do not name a
    template render the official weekly lesson plan.
    """
    from ..models import TemplateType
    return DEFAULT_TEMPLATES[0]

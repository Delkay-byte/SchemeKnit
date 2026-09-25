"""
SchemeKnit Production Data Models — Milestone 2

Complete curriculum taxonomy, curriculum profiles, advanced templates,
entitlements, content packs, and provenance tracking.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, date, time
from enum import Enum
import uuid


# ── Enums ─────────────────────────────────────────────────────────────────────

class Subject(str, Enum):
    MATHEMATICS = "Mathematics"
    SCIENCE = "Science"
    ENGLISH = "English Language"
    GHANAIAN_LANGUAGE = "Ghanaian Language"
    SOCIAL_STUDIES = "Social Studies"
    ICT = "ICT"
    RME = "Religious and Moral Education"
    PHE = "Physical and Health Education"
    CREATIVE_ARTS = "Creative Arts and Design"
    CAREER_TECHNOLOGY = "Career Technology"
    # KG / Early Childhood (the new standards-based KG curriculum)
    LANGUAGE_AND_LITERACY = "Language and Literacy"
    NUMERACY = "Numeracy"
    OUR_WORLD_OUR_PEOPLE = "Our World Our People"
    PHYSICAL_DEVELOPMENT = "Physical Development"
    # SHS (Senior High School) — core and elective subjects
    CORE_MATHEMATICS = "Core Mathematics"
    INTEGRATED_SCIENCE = "Integrated Science"
    BIOLOGY = "Biology"
    CHEMISTRY = "Chemistry"
    PHYSICS = "Physics"
    ELECTIVE_MATHEMATICS = "Elective Mathematics"
    ECONOMICS = "Economics"
    GEOGRAPHY = "Geography"
    GOVERNMENT = "Government"
    HISTORY = "History"
    LITERATURE_IN_ENGLISH = "Literature in English"
    FRENCH = "French"
    BUSINESS_MANAGEMENT = "Business Management"
    FINANCIAL_ACCOUNTING = "Financial Accounting"
    COST_ACCOUNTING = "Cost Accounting"
    GENERAL_AGRICULTURE = "General Agriculture"
    GENERAL_KNOWLEDGE_IN_ART = "General Knowledge in Art"
    #: Explicit, honest "we could not detect this" value. It is NEVER a real
    #: subject and must never be presented as one — it exists so uncertainty is
    #: represented rather than fabricated as Mathematics.
    UNKNOWN = "Unknown"


class EducationalLevel(str, Enum):
    EARLY_CHILDHOOD = "Early Childhood"
    PRIMARY = "Primary"
    JHS = "Junior High School"
    SHS = "Senior High School"


class ClassLevel(str, Enum):
    NURSERY = "Nursery"
    #: Specific nursery levels — a real N1/N2 scheme declares its exact level
    #: and keeps it (never silently collapsed to the generic family name).
    NURSERY_1 = "Nursery 1"
    NURSERY_2 = "Nursery 2"
    KG1 = "KG 1"
    KG2 = "KG 2"
    BASIC_1 = "Basic 1"
    BASIC_2 = "Basic 2"
    BASIC_3 = "Basic 3"
    BASIC_4 = "Basic 4"
    BASIC_5 = "Basic 5"
    BASIC_6 = "Basic 6"
    BASIC_7 = "Basic 7"
    BASIC_8 = "Basic 8"
    BASIC_9 = "Basic 9"
    SHS_1 = "SHS 1"
    SHS_2 = "SHS 2"
    SHS_3 = "SHS 3"
    #: Explicit "could not detect" value — never a real class level.
    UNKNOWN = "Unknown"


CLASS_LEVEL_TO_EDUCATIONAL_LEVEL = {
    ClassLevel.NURSERY: EducationalLevel.EARLY_CHILDHOOD,
    ClassLevel.KG1: EducationalLevel.EARLY_CHILDHOOD,
    ClassLevel.KG2: EducationalLevel.EARLY_CHILDHOOD,
    ClassLevel.BASIC_1: EducationalLevel.PRIMARY,
    ClassLevel.BASIC_2: EducationalLevel.PRIMARY,
    ClassLevel.BASIC_3: EducationalLevel.PRIMARY,
    ClassLevel.BASIC_4: EducationalLevel.PRIMARY,
    ClassLevel.BASIC_5: EducationalLevel.PRIMARY,
    ClassLevel.BASIC_6: EducationalLevel.PRIMARY,
    ClassLevel.BASIC_7: EducationalLevel.JHS,
    ClassLevel.BASIC_8: EducationalLevel.JHS,
    ClassLevel.BASIC_9: EducationalLevel.JHS,
    ClassLevel.SHS_1: EducationalLevel.SHS,
    ClassLevel.SHS_2: EducationalLevel.SHS,
    ClassLevel.SHS_3: EducationalLevel.SHS,
}

EDUCATIONAL_LEVEL_TO_CLASS_LEVELS = {}
for _cl, _el in CLASS_LEVEL_TO_EDUCATIONAL_LEVEL.items():
    EDUCATIONAL_LEVEL_TO_CLASS_LEVELS.setdefault(_el, []).append(_cl)


# ── Level-aware subject availability ──────────────────────────────────────────
# The single source of truth for "which subjects are available at this level".
# The UI (settings, upload, generation) reads this through the API rather than
# keeping its own list, so availability can never drift between components.

KG_SUBJECTS: List["Subject"] = [
    Subject.LANGUAGE_AND_LITERACY,
    Subject.NUMERACY,
    Subject.OUR_WORLD_OUR_PEOPLE,
    Subject.CREATIVE_ARTS,
    Subject.PHYSICAL_DEVELOPMENT,
]

PRIMARY_SUBJECTS: List["Subject"] = [
    Subject.ENGLISH,
    Subject.MATHEMATICS,
    Subject.SCIENCE,
    Subject.OUR_WORLD_OUR_PEOPLE,
    Subject.GHANAIAN_LANGUAGE,
    Subject.RME,
    Subject.CREATIVE_ARTS,
    Subject.PHE,
    Subject.ICT,
    Subject.HISTORY,
]

JHS_SUBJECTS: List["Subject"] = [
    Subject.ENGLISH,
    Subject.MATHEMATICS,
    Subject.SCIENCE,
    Subject.SOCIAL_STUDIES,
    Subject.CAREER_TECHNOLOGY,
    Subject.GHANAIAN_LANGUAGE,
    Subject.RME,
    Subject.CREATIVE_ARTS,
    Subject.ICT,
    Subject.PHE,
    Subject.FRENCH,
]

SHS_SUBJECTS: List["Subject"] = [
    Subject.ENGLISH,
    Subject.CORE_MATHEMATICS,
    Subject.INTEGRATED_SCIENCE,
    Subject.SOCIAL_STUDIES,
    Subject.BIOLOGY,
    Subject.CHEMISTRY,
    Subject.PHYSICS,
    Subject.ELECTIVE_MATHEMATICS,
    Subject.ECONOMICS,
    Subject.GEOGRAPHY,
    Subject.GOVERNMENT,
    Subject.HISTORY,
    Subject.LITERATURE_IN_ENGLISH,
    Subject.FRENCH,
    Subject.ICT,
    Subject.BUSINESS_MANAGEMENT,
    Subject.FINANCIAL_ACCOUNTING,
    Subject.COST_ACCOUNTING,
    Subject.GENERAL_AGRICULTURE,
    Subject.GENERAL_KNOWLEDGE_IN_ART,
]

#: Canonical LEVEL → AVAILABLE SUBJECTS mapping.
CLASS_LEVEL_SUBJECTS: Dict["ClassLevel", List["Subject"]] = {
    ClassLevel.NURSERY: KG_SUBJECTS,
    ClassLevel.KG1: KG_SUBJECTS,
    ClassLevel.KG2: KG_SUBJECTS,
    ClassLevel.BASIC_1: PRIMARY_SUBJECTS,
    ClassLevel.BASIC_2: PRIMARY_SUBJECTS,
    ClassLevel.BASIC_3: PRIMARY_SUBJECTS,
    ClassLevel.BASIC_4: PRIMARY_SUBJECTS,
    ClassLevel.BASIC_5: PRIMARY_SUBJECTS,
    ClassLevel.BASIC_6: PRIMARY_SUBJECTS,
    ClassLevel.BASIC_7: JHS_SUBJECTS,
    ClassLevel.BASIC_8: JHS_SUBJECTS,
    ClassLevel.BASIC_9: JHS_SUBJECTS,
    ClassLevel.SHS_1: SHS_SUBJECTS,
    ClassLevel.SHS_2: SHS_SUBJECTS,
    ClassLevel.SHS_3: SHS_SUBJECTS,
}

#: The subjects that have ever been generally available (used as a safe
#: fallback and for global checks). The explicit UNKNOWN sentinel is excluded:
#: it is a "needs confirmation" state, not an offered subject.
ALL_SUBJECTS: List["Subject"] = [s for s in Subject if s is not Subject.UNKNOWN]


def _coerce_class_level(level) -> "Optional[ClassLevel]":
    """Accept a ClassLevel, its value, or a level-like string."""
    if isinstance(level, ClassLevel):
        return level
    if not level:
        return None
    try:
        return ClassLevel(str(level))
    except ValueError:
        return None


def subjects_for_class_level(level) -> List["Subject"]:
    """Return the subjects available at a class level (level-aware).

    Accepts a ``ClassLevel`` or its string value. Falls back to all subjects
    when the level is unknown so callers never get an empty list.
    """
    cl = _coerce_class_level(level)
    if cl is None:
        return list(ALL_SUBJECTS)
    return list(CLASS_LEVEL_SUBJECTS.get(cl, ALL_SUBJECTS))


def subjects_for_educational_level(level) -> List["Subject"]:
    """Return the union of subjects across every class level in a stage."""
    el = level
    if not isinstance(el, EducationalLevel):
        try:
            el = EducationalLevel(str(level))
        except ValueError:
            return list(ALL_SUBJECTS)
    out: List["Subject"] = []
    for cl in EDUCATIONAL_LEVEL_TO_CLASS_LEVELS.get(el, []):
        for s in CLASS_LEVEL_SUBJECTS.get(cl, []):
            if s not in out:
                out.append(s)
    return out or list(ALL_SUBJECTS)


class AIMode(str, Enum):
    OFF = "OFF"
    BASIC = "BASIC"
    ENHANCED = "ENHANCED"


class TemplateType(str, Enum):
    GES_STYLE = "GES-style"
    STANDARD_PROFESSIONAL = "Standard Professional"
    MINIMAL = "Minimal"


class WeekType(str, Enum):
    INSTRUCTION = "instruction"
    REVISION = "revision"
    ASSESSMENT = "assessment"
    SBA = "sba"
    OTHER = "other"


class ValidationSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class LessonStatus(str, Enum):
    PENDING = "pending"
    GENERATED = "generated"
    REVIEWED = "reviewed"
    EDITED = "edited"
    EXPORTED = "exported"


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class ContentSource(str, Enum):
    SCHEME = "scheme"
    DETERMINISTIC = "deterministic"
    AI = "ai"
    TEACHER = "teacher"
    TEMPLATE = "template"
    DEFAULT = "default"


class ProductEdition(str, Enum):
    FREE = "free"
    TEACHER = "teacher"
    SCHOOL = "school"


# ── Curriculum Profile ────────────────────────────────────────────────────────

class CurriculumProfileField(BaseModel):
    name: str
    label: str
    field_type: str = "text"
    required: bool = False
    visible: bool = True
    order: int = 0
    source: ContentSource = ContentSource.DETERMINISTIC


class CurriculumProfile(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    educational_level: EducationalLevel
    description: str = ""
    supported_class_levels: List[ClassLevel] = []
    scheme_structure: Dict[str, Any] = {}
    lesson_plan_fields: List[CurriculumProfileField] = []
    standard_terminology: Dict[str, str] = {}
    assessment_expectations: List[str] = []
    template_family: str = ""
    generation_rules: Dict[str, Any] = {}
    validation_rules: Dict[str, Any] = {}
    ai_behavior: Dict[str, Any] = {}


# ── Template System ──────────────────────────────────────────────────────────

class TemplateFamily(str, Enum):
    EARLY_CHILDHOOD = "early_childhood"
    PRIMARY = "primary"
    JHS = "jhs"
    SHS = "shs"


class TemplateFieldType(str, Enum):
    TEXT = "text"
    TEXTAREA = "textarea"
    DATE = "date"
    NUMBER = "number"
    SELECT = "select"
    TABLE = "table"
    RICH_TEXT = "rich_text"


class TemplateField(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    label: str
    field_type: TemplateFieldType = TemplateFieldType.TEXT
    required: bool = False
    visible: bool = True
    order: int = 0
    placeholder: str = ""
    default_value: str = ""
    options: List[str] = []
    source: ContentSource = ContentSource.DETERMINISTIC


class TemplateSection(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    label: str
    visible: bool = True
    required: bool = True
    order: int = 0
    fields: List[TemplateField] = []
    collapsible: bool = False
    description: str = ""


class TemplateLayout(BaseModel):
    page_size: str = "A4"
    orientation: str = "portrait"
    margins_top: float = 2.54
    margins_bottom: float = 2.54
    margins_left: float = 2.54
    margins_right: float = 2.54
    font_family: str = "Arial"
    font_size: int = 11
    heading_font_size: int = 14
    line_spacing: float = 1.15
    table_border_width: float = 0.5
    table_header_bg: str = "003366"
    table_header_fg: str = "FFFFFF"
    page_break_between_lessons: bool = True


class Template(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    family: TemplateFamily
    educational_level: EducationalLevel
    description: str = ""
    features: List[str] = []
    sections: List[TemplateSection] = []
    layout: TemplateLayout = TemplateLayout()
    is_default: bool = False
    is_official: bool = False
    version: str = "1.0"
    author: str = "SchemeKnit"
    preview_path: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


# ── Parse / Ingestion Models ──────────────────────────────────────────────────

class ValidationIssue(BaseModel):
    severity: ValidationSeverity
    field: Optional[str] = None
    row_index: Optional[int] = None
    message: str


class ParsedContentStandard(BaseModel):
    code: str
    description: str


class ParsedIndicator(BaseModel):
    code: str
    description: str


class ParsedWeek(BaseModel):
    week_number: int
    week_ending: Optional[date] = None
    week_type: WeekType = WeekType.INSTRUCTION
    strand: Optional[str] = None
    sub_strand: Optional[str] = None
    content_standards: List[ParsedContentStandard] = []
    indicators: List[ParsedIndicator] = []
    resources: List[str] = []


class ParsedScheme(BaseModel):
    filename: str
    subject: Optional[str] = None
    class_level: Optional[str] = None
    term: Optional[str] = None
    academic_year: Optional[str] = None
    weeks: List[ParsedWeek] = []
    validation_issues: List[ValidationIssue] = []
    raw_tables: List[List[List[str]]] = []


# ── Scheme Models ─────────────────────────────────────────────────────────────

class Week(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    week_number: int
    start_date: date
    end_date: date
    #: True when end_date was NOT present in the source document and had to
    #: be derived. Source dates are authoritative; derived dates must be
    #: labelled as such through parse → allocation → generation → export.
    week_ending_derived: bool = False
    week_type: WeekType = WeekType.INSTRUCTION
    strand: Optional[str] = None
    sub_strand: Optional[str] = None
    content_standards: List[str] = []
    indicators: List[str] = []
    resources: List[str] = []
    strands: List[Any] = []
    scheme_of_work_id: str


class SchemeOfWork(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    filename: str
    upload_date: datetime
    subject: Subject
    class_level: ClassLevel
    term: str
    academic_year: str
    weeks: List[Week] = []
    raw_text: Optional[str] = None
    status: str = "uploaded"
    validation_issues: List[ValidationIssue] = []


# ── Term Configuration ────────────────────────────────────────────────────────

class Holiday(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    date: date
    is_recurring: bool = False
    description: Optional[str] = None


class TermConfig(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    scheme_of_work_id: str
    academic_year: str = "2026/2027"
    term: str = "First Term"
    # Defaults are explicitly UNKNOWN: a config missing a level/subject must
    # never silently become Basic 9 / Science (PART E/Y).
    class_level: ClassLevel = ClassLevel.UNKNOWN
    subject: Subject = Subject.UNKNOWN
    class_size: int = 24
    lesson_duration_minutes: int = 60
    lessons_per_week: int = 3
    term_start_date: date = Field(default_factory=date.today)
    term_end_date: date = Field(default_factory=date.today)
    teaching_days: List[int] = [0, 2, 4]
    holidays: List[Holiday] = []
    school_name: Optional[str] = None
    teacher_name: Optional[str] = None
    template_id: Optional[str] = None
    ai_mode: AIMode = AIMode.OFF
    include_special_weeks: bool = False
    #: Free-Tier selection: the exact indicator codes the teacher chose to
    #: generate this month. Empty means "everything in curriculum order".
    #: Selecting a subset NEVER reorders the curriculum — the allocation keeps
    #: source week, teaching week, indicator code/text, sequence and
    #: carry-forward state; only the chosen indicators are generated.
    selected_indicator_codes: List[str] = []
    # Teacher-supplied lesson metadata (PART 11-24). Each is optional and blanks
    # are preserved as blank — the generator never invents values for them.
    period: str = ""
    keywords: List[str] = []
    teaching_learning_resources: List[str] = []
    core_competencies: List[str] = []
    references: List[str] = []
    created_date: datetime = Field(default_factory=datetime.now)


# ── Teaching Calendar ─────────────────────────────────────────────────────────

class TeachingDay(BaseModel):
    date: date
    day_of_week: int
    is_teaching_day: bool
    is_holiday: bool
    holiday_name: Optional[str] = None
    week_number: Optional[int] = None
    week_ending: Optional[date] = None
    lesson_slot: int = 0


class TeachingCalendar(BaseModel):
    term_start: date
    term_end: date
    teaching_days: List[int]
    holidays: Dict[date, str] = {}
    days: List[TeachingDay] = []
    total_teaching_days: int = 0
    total_lessons: int = 0


# ── Curriculum Allocation ─────────────────────────────────────────────────────

class AllocatedIndicator(BaseModel):
    indicator_code: str
    indicator_description: str
    content_standard_code: str
    content_standard_description: str
    strand: str
    sub_strand: str
    #: Source curriculum week — the week the indicator belongs to in the scheme.
    week_number: int
    week_ending: Optional[date] = None
    week_ending_derived: bool = False
    #: TLRs from THIS subject + source week (never another subject/week).
    source_resources: List[str] = []
    lesson_date: Optional[date] = None
    lesson_sequence: int = 0
    # Position of this indicator within its actual teaching week (1-based).
    # Period 1 = first lesson of the teaching week, Period 2 = second, etc.
    period_index: int = 0
    allocated: bool = False
    #: Actual teaching week the lesson is delivered in. Equal to week_number
    #: when no carry-forward was required, otherwise a later teaching week.
    teaching_week: int = 0
    #: True when the indicator carried forward out of its source week because
    #: that week had more indicators than available teaching periods.
    carry_forward: bool = False
    #: The source week the indicator carried forward from (None when not moved).
    carry_forward_from_week: Optional[int] = None
    #: True when the indicator could not be placed on a real teaching date
    #: (e.g. the term has no further teaching periods) and needs teacher review.
    needs_review: bool = False


class CurriculumCoverage(BaseModel):
    total_instructional_weeks: int = 0
    total_indicators: int = 0
    total_generated_lessons: int = 0
    total_periods_allocated: int = 0
    indicators_allocated: int = 0
    indicators_unallocated: int = 0
    indicators_duplicated: int = 0
    coverage_percentage: float = 0.0
    allocations: List[AllocatedIndicator] = []
    warnings: List[str] = []
    # Allocation conflicts: e.g. "Week 1 contains 3 indicators but only 2
    # teaching periods are configured." These are NOT silently resolved —
    # they are surfaced to the teacher before generation.
    allocation_conflicts: List[str] = []


# ── Lesson Plan ───────────────────────────────────────────────────────────────

class LearningObjective(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str
    indicator_code: Optional[str] = None
    source: ContentSource = ContentSource.DETERMINISTIC


class TeachingActivity(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    phase: str
    description: str
    duration_minutes: int = 0
    resources: List[str] = []
    source: ContentSource = ContentSource.DETERMINISTIC


class ReferenceEntry(BaseModel):
    """One structured, teacher-controlled reference for a single lesson.

    Page numbers and textbook titles are NEVER invented — blank means the
    teacher has not supplied them.
    """
    type: str = "Other"  # Subject Curriculum | Teacher's Handbook / Teacher's Guide | Textbook | Other
    title: str = ""
    author_publisher: str = ""
    page: str = ""
    notes: str = ""


#: Official NaCCA core-competency taxonomy (canonical labels + codes).
NACCA_CORE_COMPETENCIES: List[Dict[str, str]] = [
    {"code": "CP", "label": "Critical Thinking and Problem Solving"},
    {"code": "CI", "label": "Creativity and Innovation"},
    {"code": "CC", "label": "Communication and Collaboration"},
    {"code": "CG", "label": "Cultural Identity and Global Citizenship"},
    {"code": "PL", "label": "Personal Development and Leadership"},
    {"code": "DL", "label": "Digital Literacy"},
]
NACCA_COMPETENCY_LABELS: List[str] = [c["label"] for c in NACCA_CORE_COMPETENCIES]


class LessonPlan(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    scheme_of_work_id: str
    term_config_id: str
    #: WAPEF teacher-selected structured fields (Approved WAPEF Plan). Optional
    #: so existing lessons stay valid; never AI-chosen, never overwritten by
    #: generation. See engines/wapef_fields.py for the approved option lists.
    wapef_deep_hope: str = ""
    wapef_storyline: str = ""
    #: Selected Through lines in APPROVED ORDER (export order).
    wapef_through_lines: List[str] = []
    wapef_gods_story: str = ""
    #: Teacher-written remarks (WAPEF REMARKS row); blank when not written.
    remarks: str = ""
    #: Source curriculum week the lesson's indicator belongs to.
    week_number: int
    #: Source week-ending date for that curriculum week. Authoritative when
    #: the document supplied it; export must not recompute over this value.
    week_ending: Optional[date] = None
    #: True when week_ending was derived because the source omitted a date.
    week_ending_derived: bool = False
    lesson_sequence: int
    lesson_date: date
    lesson_number: int = 0
    #: Actual teaching week the lesson is delivered in. Retains the link to the
    #: source curriculum week via ``week_number`` while representing when the
    #: teacher is actually scheduled to teach it.
    teaching_week: int = 0
    #: True when this lesson carries an indicator forward from an earlier
    #: source week.
    carry_forward: bool = False
    # Timetable slot, e.g. "1st & 2nd". Teacher-configured; never invented.
    period: str = ""

    educational_level: EducationalLevel = EducationalLevel.JHS
    class_level: ClassLevel = ClassLevel.UNKNOWN
    subject: Subject = Subject.UNKNOWN
    class_size: int = 24
    duration_minutes: int = 60
    school_name: Optional[str] = None
    teacher_name: Optional[str] = None

    strand: Optional[str] = None
    sub_strand: Optional[str] = None
    content_standard: Optional[str] = None
    content_standard_code: Optional[str] = None
    indicators: List[str] = []
    indicator_codes: List[str] = []

    lesson_topic: str = ""
    essential_questions: List[str] = []
    previous_knowledge: str = ""
    #: Lesson-specific vocabulary. Derived from content standard + exact
    #: indicator + activity context; teacher-entered terms are authoritative.
    keywords: List[str] = []
    learning_objectives: List[LearningObjective] = []
    #: Per-lesson multi-select from the official NaCCA taxonomy.
    core_competencies: List[str] = []
    #: TLRs FROM THE SCHEME for this subject + source week + indicator.
    #: Authoritative curriculum-source data — never from another subject/week.
    source_tlrs: List[str] = []
    #: Teacher-added resources for THIS lesson only. Never merged with source.
    other_tlrs: List[str] = []
    #: Display union for templates that expect one TLR list. Built from
    #: source_tlrs + other_tlrs at render time when source fields are set;
    #: kept in sync so existing export paths stay green.
    teaching_learning_resources: List[str] = []

    introduction: str = ""
    starter_activity: str = ""
    main_activities: List[TeachingActivity] = []
    learner_activities: List[TeachingActivity] = []
    teacher_activities: List[TeachingActivity] = []
    group_work: str = ""
    individual_work: str = ""
    assessment: str = ""
    differentiation: str = ""
    remediation: str = ""
    extension: str = ""
    conclusion: str = ""
    reflection: str = ""
    homework: str = ""
    #: Structured, per-lesson references (type/title/author/page/notes).
    structured_references: List[ReferenceEntry] = []
    #: Flat string form for existing templates/export paths.
    references: List[str] = []

    status: LessonStatus = LessonStatus.PENDING
    ai_generated: bool = False
    teacher_edited: bool = False
    template_id: Optional[str] = None
    created_date: datetime = Field(default_factory=datetime.now)
    updated_date: datetime = Field(default_factory=datetime.now)


# ── Weekly class-teacher plan (Approved WAPEF Basic 1-3 Plan) ─────────────────
#
# Basic 1-3 is the CLASS-TEACHER model: one teacher teaches several subjects on
# different days inside the SAME weekly plan. One weekly plan therefore holds
# several subject sections, and each section holds one day plan per teaching-day
# group (a single day, or several days grouped into one shared entry such as
# the supplied Basic 1 plan's "MONDAY & THURSDAY" RME row).
#
# The day plan is NOT a relabelled lesson: DAYS is a first-class structural
# column (DAYS | PHASE 1: STARTER | PHASE 2: MAIN | PHASE 3: REFLECTION) and
# each day carries its own starter/main/reflection content. Subject metadata is
# shared across that subject's day plans and is stored once per plan section
# (see engines/weekly_plan_engine.py).


class DayPlan(BaseModel):
    """One teaching-day entry in a week's subject section."""

    #: The stored lesson row that carries this day plan (canonical lesson object).
    lesson_plan_id: Optional[str] = None
    #: Canonical uppercase day names, week order. One entry for a normal day,
    #: several when the teacher groups days into one shared teaching entry.
    days: List[str] = []
    #: The export label the source prints ("MONDAY", "MONDAY & THURSDAY").
    day_label: str = ""
    #: Curriculum focus for this day (never invented; repeated only when the
    #: source week has fewer indicators than teaching days).
    focus_indicators: List[str] = []
    focus_indicator_codes: List[str] = []
    starter: str = ""
    main_activities: List[TeachingActivity] = []
    reflection: str = ""
    resources: List[str] = []
    lesson_date: Optional[date] = None
    period: str = ""


class SubjectMetadata(BaseModel):
    """Curriculum + WAPEF metadata shared by one subject's day plans.

    Every field is optional: the source's subject sections differ from one
    another (some carry Strand/Sub strand, some do not), and a value the scheme
    never supplied stays blank rather than being fabricated.
    """

    subject: str = ""
    class_level: str = ""
    week_number: int = 0
    week_ending: Optional[date] = None
    week_ending_derived: bool = False
    reference: str = ""
    strand: str = ""
    sub_strand: str = ""
    content_standards: List[str] = []
    content_standard_codes: List[str] = []
    indicators: List[str] = []
    indicator_codes: List[str] = []
    performance_indicators: List[str] = []
    teaching_learning_resources: List[str] = []
    core_competencies: List[str] = []
    keywords: List[str] = []
    wapef_deep_hope: str = ""
    wapef_storyline: str = ""
    wapef_through_lines: List[str] = []
    wapef_gods_story: str = ""


class SubjectPlan(BaseModel):
    """One subject section of a weekly class plan."""

    scheme_of_work_id: str = ""
    job_id: str = ""
    subject: str = ""
    #: Every declared teaching day of the week, in week order.
    teaching_days: List[str] = []
    #: The declared teaching-day groups, in week order. Each inner list is one
    #: shared teaching entry ("["MONDAY", "THURSDAY"]").
    teaching_day_groups: List[List[str]] = []
    metadata: SubjectMetadata = SubjectMetadata()
    day_plans: List[DayPlan] = []


class WeeklyClassPlan(BaseModel):
    """One weekly class-teacher plan holding every subject of the class."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    owner_id: str = ""
    class_level: ClassLevel = ClassLevel.UNKNOWN
    week_number: int = 0
    term: str = ""
    academic_year: str = ""
    term_start_date: Optional[date] = None
    term_end_date: Optional[date] = None
    school_name: Optional[str] = None
    teacher_name: Optional[str] = None
    template_id: str = ""
    subjects: List[SubjectPlan] = []
    created_date: datetime = Field(default_factory=datetime.now)
    updated_date: datetime = Field(default_factory=datetime.now)


class WeeklyPlanSubjectRequest(BaseModel):
    """One subject the class teacher wants in this week's plan."""

    scheme_id: str
    #: Teacher-confirmed teaching-day groups. Empty means "every weekday the
    #: subject's scheme week has content for" is NOT assumed: the teacher's
    #: selection is authoritative and an empty selection is rejected.
    teaching_day_groups: List[List[str]] = []
    wapef_deep_hope: str = ""
    wapef_storyline: str = ""
    wapef_through_lines: List[str] = []
    wapef_gods_story: str = ""
    keywords: List[str] = []
    core_competencies: List[str] = []
    other_tlrs: List[str] = []


class WeeklyPlanRequest(BaseModel):
    """Request body for generating one Basic 1-3 weekly class plan."""

    class_level: ClassLevel = ClassLevel.UNKNOWN
    week_number: int = 1
    term_start_date: date = Field(default_factory=date.today)
    term_end_date: date = Field(default_factory=date.today)
    term: str = ""
    academic_year: str = "2026/2027"
    class_size: int = 24
    lesson_duration_minutes: int = 60
    include_special_weeks: bool = False
    ai_mode: AIMode = AIMode.OFF
    subjects: List[WeeklyPlanSubjectRequest] = []


# ── Generation Job ────────────────────────────────────────────────────────────

class GenerationJob(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    config: Optional[TermConfig] = None
    scheme_of_work_id: str
    status: JobStatus = JobStatus.PENDING
    progress: float = 0.0
    total_lessons: int = 0
    completed_lessons: int = 0
    failed_lessons: int = 0
    remaining_lessons: int = 0
    created_date: datetime = Field(default_factory=datetime.now)
    completed_date: Optional[datetime] = None
    error_message: Optional[str] = None
    result_files: List[str] = []
    lesson_plan_ids: List[str] = []
    ai_enrichment_errors: Dict[str, str] = {}
    ai_enrichment_total_attempted: int = 0
    ai_enrichment_succeeded: int = 0


# ── AI Enrichment ─────────────────────────────────────────────────────────────

class AIEnrichmentRequest(BaseModel):
    lesson_plan_id: str
    section: str
    educational_level: EducationalLevel
    class_level: ClassLevel
    subject: Subject
    strand: str = ""
    sub_strand: str = ""
    content_standard: str = ""
    indicator: str = ""
    lesson_duration: int = 60
    class_size: int = 24
    resources: List[str] = []
    previous_knowledge: str = ""
    existing_content: str = ""


class AIEnrichmentResponse(BaseModel):
    section: str
    content: str
    source: ContentSource = ContentSource.AI
    provider: str = ""
    token_usage: int = 0
    cached: bool = False


class SectionRegenerationRequest(BaseModel):
    lesson_plan_id: str
    sections: List[str]
    ai_mode: AIMode = AIMode.BASIC


# ── Entitlement / Product Edition ─────────────────────────────────────────────

class FeatureFlag(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    enabled: bool = True
    editions: List[ProductEdition] = [ProductEdition.FREE]


class Entitlement(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    edition: ProductEdition = ProductEdition.FREE
    features: List[str] = []
    max_schemes: int = 5
    max_lessons_per_scheme: int = 50
    max_templates: int = 3
    ai_enabled: bool = False
    advanced_ai_enabled: bool = False
    cloud_sync: bool = False
    template_import: bool = False
    content_library: bool = False
    expires_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.now)
    # Individual teacher plan fields (v013)
    subscription_type: Optional[str] = None  # individual | school | null
    generation_limit: int = 0  # 0 = unlimited
    generations_used: int = 0
    batch_generation: bool = False
    zip_export: bool = False
    pdf_export: bool = True
    custom_template_limit: int = 3
    history_limit: int = 10
    ai_credits: int = 0  # 0 = unlimited or disabled
    ai_credits_used: int = 0


class Subscription(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    edition: ProductEdition
    plan_name: str = ""
    status: str = "active"
    started_at: datetime = Field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    payment_provider: str = ""
    external_id: str = ""


# ── Content Pack ──────────────────────────────────────────────────────────────

class ContentPack(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    class_level: ClassLevel
    subject: Subject
    term: str
    academic_year: str
    educational_level: EducationalLevel
    template_family: TemplateFamily
    version: str = "1.0"
    author: str = "SchemeKnit"
    is_official: bool = False
    is_premium: bool = False
    price: float = 0.0
    lesson_count: int = 0
    preview_path: Optional[str] = None
    status: str = "active"
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class ContentPackLesson(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    pack_id: str
    lesson_plan_id: str
    week_number: int
    lesson_sequence: int
    preview_text: str = ""


class ContentPackPurchase(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    pack_id: str
    version: str = "1.0"
    purchased_at: datetime = Field(default_factory=datetime.now)
    download_count: int = 0


# ── Payment Models ────────────────────────────────────────────────────────────

class PaymentMethod(str, Enum):
    MTN_MOMO = "mtn_momo"
    BANK_TRANSFER = "bank_transfer"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class ProductType(str, Enum):
    SUBSCRIPTION = "subscription"
    CONTENT_PACK = "content_pack"
    CUSTOM_GENERATION = "custom_generation"
    SOFTWARE_LICENSE = "software_license"
    TEMPLATE = "template"
    OTHER = "other"


class Payment(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    payment_method: PaymentMethod
    amount: float = Field(ge=0)
    currency: str = "GHS"
    product_type: ProductType
    product_id: str
    product_name: str = ""
    reference: str = ""
    payer_name: str = ""
    payer_phone: str = ""
    proof_path: Optional[str] = None
    notes: str = ""
    status: PaymentStatus = PaymentStatus.PENDING
    submitted_at: datetime = Field(default_factory=datetime.now)
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None
    rejection_reason: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class PaymentAuditLog(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    payment_id: str
    user_id: str
    action: str
    old_status: Optional[PaymentStatus] = None
    new_status: PaymentStatus
    amount: float = 0.0
    currency: str = "GHS"
    product_type: str = ""
    product_id: str = ""
    payment_method: str = ""
    performed_by: str = ""
    notes: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)


# ── Product / Plan Configuration ──────────────────────────────────────────────

class ProductPlan(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    product_type: ProductType
    price: float = Field(ge=0)
    currency: str = "GHS"
    duration_days: Optional[int] = None
    features: List[str] = []
    educational_levels: List[str] = []
    template_access: List[str] = []
    ai_access: str = ""
    content_access: List[str] = []
    active: bool = True
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    # Individual teacher plan fields (v013)
    customer_type: str = "school"  # school | individual_teacher
    generation_limit: int = 0  # 0 = unlimited
    batch_generation: bool = False
    zip_export: bool = False
    pdf_export: bool = False
    custom_template_limit: int = 0
    history_limit: int = 0
    ai_enabled: bool = False
    ai_credits: int = 0
    max_generations_per_period: int = 0  # 0 = unlimited


class PaymentConfig(BaseModel):
    """Configurable payment instructions. Admin-editable."""
    mtn_momo: Dict[str, Any] = {
        "phone": "0553976334",
        "account_name": "Kobla Saviour Amegayie",
        "enabled": True,
    }
    bank_transfer: Dict[str, Any] = {
        "bank": "GCB Bank",
        "account_number": "5151010019541",
        "branch": "Abor",
        "account_name": "Kobla Saviour Amegayie",
        "enabled": True,
    }
    currency: str = "GHS"
    updated_at: datetime = Field(default_factory=datetime.now)


# ── Admin Role ────────────────────────────────────────────────────────────────

class AdminRole(str, Enum):
    SUPER_ADMIN = "super_admin"
    PAYMENT_ADMIN = "payment_admin"
    CONTENT_ADMIN = "content_admin"

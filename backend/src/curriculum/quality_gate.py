"""
SchemeKnit Lesson Quality Gate
================================

Validates a generated lesson plan against curriculum fidelity, pedagogical
coherence, and practical quality criteria.

A lesson that fails the quality gate is flagged for review or regeneration.
No lesson is silently returned with poor quality.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from . import Indicator, CurriculumWeekType
from .indicator_interpreter import IndicatorInterpretation


class QualityStatus:
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass
class QualityIssue:
    """A single quality check result."""
    check_name: str
    status: str  # QualityStatus.PASS / WARN / FAIL
    message: str
    severity: str = "error"  # error / warning / info
    category: str = ""  # curriculum / objectives / activities / assessment / coherence / practicality


@dataclass
class QualityReport:
    """Aggregated quality validation report for a lesson plan."""
    overall_status: str = QualityStatus.PASS
    issues: List[QualityIssue] = field(default_factory=list)
    score: float = 0.0  # 0-100

    @property
    def passed(self) -> bool:
        return self.overall_status != QualityStatus.FAIL

    @property
    def failures(self) -> List[QualityIssue]:
        return [i for i in self.issues if i.status == QualityStatus.FAIL]

    @property
    def warnings(self) -> List[QualityIssue]:
        return [i for i in self.issues if i.status == QualityStatus.WARN]

    def summary(self) -> Dict[str, Any]:
        return {
            "status": self.overall_status,
            "score": self.score,
            "total_checks": len(self.issues),
            "failures": len(self.failures),
            "warnings": len(self.warnings),
            "failure_messages": [i.message for i in self.failures],
            "warning_messages": [i.message for i in self.warnings],
        }


# ── Validation Functions ──────────────────────────────────────────────────

# Verbs matched as whole words (with common inflections), never as substrings:
# a substring test flags "learn" inside "learners/learning" and "use" inside
# "because/excuse" — the two classic false positives seen in real generations.
_VAGUE_VERBS = ("understand", "know", "appreciate", "learn", "be aware of", "familiarize")

# Bloom-level measurable verbs, including the ones used in real GES indicators
# (express/round/model/state/name/match/estimate/order/label/order...).
_MEASURABLE_VERBS = (
    "identify", "classify", "calculate", "compute", "compare", "contrast",
    "explain", "construct", "demonstrate", "analyze", "analyse", "create",
    "justify", "describe", "list", "define", "solve", "apply", "examine",
    "investigate", "discuss", "design", "evaluate", "measure", "record",
    "draw", "write", "read", "speak", "listen", "perform", "practise",
    "practice", "state", "name", "match", "label", "round", "express",
    "model", "estimate", "order", "sort", "group", "represent", "sketch",
    "build", "prepare", "follow", "trace", "recall", "predict", "test",
    "experiment", "gather", "choose", "select", "outline", "organize",
    "organise", "relate", "summarise", "summarize", "convert", "translate",
    "substitute", "change", "reorder", "rewrite",
    "use",
)

_INFLECTION = r"(?:s|es|ed|ing)?"


def _verb_pattern(word: str) -> "re.Pattern[str]":
    if " " in word:
        return re.compile(rf"\b{'\\s+'.join(re.escape(p) for p in word.split())}\b")
    esc = re.escape(word)
    if word.endswith("e"):
        return re.compile(
            rf"\b(?:{esc}(?:s|es|ed|ing)?|{esc[:-1]}(?:ing|ed))\b"
        )
    return re.compile(rf"\b{esc}{_INFLECTION}\b")


_VAGUE_PATTERNS = [(_verb_pattern(v), v) for v in _VAGUE_VERBS]
_MEASURABLE_PATTERNS = [_verb_pattern(v) for v in _MEASURABLE_VERBS]


def _normalize_subject(subject: str) -> str:
    """Fold enum-style subject rendering ('Subject.Mathematics',
    'MATHEMATICS') down to the pedagogy-registry key ('mathematics')."""
    s = (subject or "").strip().lower()
    if s.startswith("subject."):
        s = s[len("subject."):]
    return s.replace("_", " ").strip()

def _check_curriculum_match(lesson: Dict[str, Any], indicator: Indicator) -> List[QualityIssue]:
    """Verify curriculum identity fields match the source indicator."""
    issues = []

    # Exact indicator code match
    lesson_codes = lesson.get("indicator_codes", [])
    if indicator.code and indicator.code not in lesson_codes:
        issues.append(QualityIssue(
            check_name="indicator_code_match",
            status=QualityStatus.FAIL,
            message=f"Indicator code mismatch: lesson has {lesson_codes}, expected {indicator.code}",
            severity="error",
            category="curriculum",
        ))
    else:
        issues.append(QualityIssue(
            check_name="indicator_code_match",
            status=QualityStatus.PASS,
            message="Indicator code matches source.",
            category="curriculum",
        ))

    # Subject match
    lesson_subject = lesson.get("subject", "").lower()
    if indicator.source_subject.lower() not in lesson_subject and lesson_subject not in indicator.source_subject.lower():
        issues.append(QualityIssue(
            check_name="subject_match",
            status=QualityStatus.WARN,
            message=f"Subject mismatch: lesson has '{lesson.get('subject')}', indicator is from '{indicator.source_subject}'",
            severity="warning",
            category="curriculum",
        ))
    else:
        issues.append(QualityIssue(
            check_name="subject_match",
            status=QualityStatus.PASS,
            message="Subject matches.",
            category="curriculum",
        ))

    # Strand match — compare the lesson strand against the SOURCE indicator's
    # strand when provided. The Indicator dataclass has no strand field, so a
    # source_strand key on the lesson dict (set by the pipeline from the
    # allocation) is used; a missing source is a PASS (nothing to compare).
    lesson_strand = (lesson.get("strand") or "").lower().strip()
    source_strand = (lesson.get("source_strand") or "").lower().strip()
    if lesson_strand and source_strand and lesson_strand != source_strand:
        issues.append(QualityIssue(
            check_name="strand_match",
            status=QualityStatus.WARN,
            message=f"Strand mismatch: lesson has '{lesson.get('strand')}', source is '{lesson.get('source_strand')}'",
            severity="warning",
            category="curriculum",
        ))
    else:
        issues.append(QualityIssue(
            check_name="strand_match",
            status=QualityStatus.PASS,
            message="Strand matches.",
            category="curriculum",
        ))

    return issues


def _check_objectives(lesson: Dict[str, Any]) -> List[QualityIssue]:
    """Validate learning objectives are measurable and traceable."""
    issues = []
    objectives = lesson.get("learning_objectives", [])

    if not objectives:
        issues.append(QualityIssue(
            check_name="has_objectives",
            status=QualityStatus.FAIL,
            message="No learning objectives found.",
            severity="error",
            category="objectives",
        ))
        return issues

    issues.append(QualityIssue(
        check_name="has_objectives",
        status=QualityStatus.PASS,
        message=f"Found {len(objectives)} learning objective(s).",
        category="objectives",
    ))

    # Check for measurable verbs
    for obj in objectives:
        if isinstance(obj, dict):
            desc = obj.get("description", "")
        elif isinstance(obj, str):
            desc = obj
        else:
            continue

        desc_lower = desc.lower()
        has_learner_can = "learners can" in desc_lower or "students can" in desc_lower

        if not has_learner_can:
            issues.append(QualityIssue(
                check_name="objectives_learner_can",
                status=QualityStatus.WARN,
                message=f"Objective should start with 'Learners can': {desc[:80]}",
                severity="warning",
                category="objectives",
            ))

        # Check for vague verbs (whole words only)
        for pattern, vague in _VAGUE_PATTERNS:
            if pattern.search(desc_lower):
                issues.append(QualityIssue(
                    check_name="objectives_measurable",
                    status=QualityStatus.WARN,
                    message=f"Objective may use vague verb '{vague}': {desc[:80]}",
                    severity="warning",
                    category="objectives",
                ))

        # Check for at least one measurable verb (whole words only)
        has_measurable = any(p.search(desc_lower) for p in _MEASURABLE_PATTERNS)
        if not has_measurable and has_learner_can:
            issues.append(QualityIssue(
                check_name="objectives_measurable_verb",
                status=QualityStatus.WARN,
                message=f"Objective may lack measurable verb: {desc[:80]}",
                severity="warning",
                category="objectives",
            ))

    if not any(i.status == QualityStatus.FAIL for i in issues if i.check_name.startswith("objectives")):
        issues.append(QualityIssue(
            check_name="objectives_quality",
            status=QualityStatus.PASS,
            message="Objectives appear measurable.",
            category="objectives",
        ))

    return issues


def _check_activities(lesson: Dict[str, Any]) -> List[QualityIssue]:
    """Validate activities address objectives and are realistic."""
    issues = []

    main_activities = lesson.get("main_activities", [])
    assessment = lesson.get("assessment", "")

    if not main_activities:
        issues.append(QualityIssue(
            check_name="has_main_activities",
            status=QualityStatus.FAIL,
            message="No main activities found.",
            severity="error",
            category="activities",
        ))
        return issues

    issues.append(QualityIssue(
        check_name="has_main_activities",
        status=QualityStatus.PASS,
        message=f"Found {len(main_activities)} main activity/activities.",
        category="activities",
    ))

    # Check teacher and learner actions are explicit
    for i, act in enumerate(main_activities):
        if isinstance(act, dict):
            desc = act.get("description", "")
        elif isinstance(act, str):
            desc = act
        else:
            continue

        if len(desc) < 20:
            issues.append(QualityIssue(
                check_name=f"activity_{i}_detail",
                status=QualityStatus.WARN,
                message=f"Activity {i+1} may lack detail ({len(desc)} chars).",
                severity="warning",
                category="activities",
            ))

    # Check timing is valid
    total_duration = 0
    for act in main_activities:
        if isinstance(act, dict):
            dur = act.get("duration_minutes", 0)
            if dur > 0:
                total_duration += dur

    lesson_duration = lesson.get("duration_minutes", 60)
    if total_duration > lesson_duration * 1.2:
        issues.append(QualityIssue(
            check_name="timing_valid",
            status=QualityStatus.WARN,
            message=f"Activity total ({total_duration}min) exceeds lesson duration ({lesson_duration}min).",
            severity="warning",
            category="activities",
        ))
    else:
        issues.append(QualityIssue(
            check_name="timing_valid",
            status=QualityStatus.PASS,
            message="Activity timing is within lesson duration.",
            category="activities",
        ))

    return issues


def _check_assessment(lesson: Dict[str, Any]) -> List[QualityIssue]:
    """Validate assessment checks the indicator and objectives."""
    issues = []
    assessment = lesson.get("assessment", "")

    if not assessment:
        issues.append(QualityIssue(
            check_name="has_assessment",
            status=QualityStatus.FAIL,
            message="No assessment found.",
            severity="error",
            category="assessment",
        ))
        return issues

    issues.append(QualityIssue(
        check_name="has_assessment",
        status=QualityStatus.PASS,
        message="Assessment section present.",
        category="assessment",
    ))

    # Check assessment is not generic
    generic_phrases = ["what did we learn today", "what do you think",
                       "any questions", "discuss generally"]
    is_generic = any(phrase in assessment.lower() for phrase in generic_phrases)
    if is_generic:
        issues.append(QualityIssue(
            check_name="assessment_specific",
            status=QualityStatus.WARN,
            message="Assessment may be too generic. Should check the specific indicator.",
            severity="warning",
            category="assessment",
        ))
    else:
        issues.append(QualityIssue(
            check_name="assessment_specific",
            status=QualityStatus.PASS,
            message="Assessment appears specific to the lesson content.",
            category="assessment",
        ))

    return issues


def _check_coherence(lesson: Dict[str, Any]) -> List[QualityIssue]:
    """Validate lesson phases connect logically."""
    issues = []

    starter = lesson.get("starter_activity", lesson.get("introduction", ""))
    main = lesson.get("main_activities", [])
    assessment = lesson.get("assessment", "")
    conclusion = lesson.get("conclusion", "")

    # Starter exists
    if not starter:
        issues.append(QualityIssue(
            check_name="has_starter",
            status=QualityStatus.WARN,
            message="No starter/introduction found.",
            severity="warning",
            category="coherence",
        ))
    else:
        issues.append(QualityIssue(
            check_name="has_starter",
            status=QualityStatus.PASS,
            message="Starter/introduction present.",
            category="coherence",
        ))

    # Conclusion exists
    if not conclusion:
        issues.append(QualityIssue(
            check_name="has_conclusion",
            status=QualityStatus.WARN,
            message="No conclusion/plenary found.",
            severity="warning",
            category="coherence",
        ))
    else:
        issues.append(QualityIssue(
            check_name="has_conclusion",
            status=QualityStatus.PASS,
            message="Conclusion/plenary present.",
            category="coherence",
        ))

    return issues


def _check_practicality(lesson: Dict[str, Any]) -> List[QualityIssue]:
    """Validate lesson is practical for Ghanaian classrooms."""
    issues = []

    # Check no expensive equipment assumptions
    expensive_keywords = ["projector", "smartboard", "computer lab", "internet access",
                          "laptop", "tablet", "digital device", "laboratory equipment"]
    all_text = " ".join([
        str(lesson.get("introduction", "")),
        str(lesson.get("assessment", "")),
        str(lesson.get("conclusion", "")),
    ])
    for act in lesson.get("main_activities", []):
        if isinstance(act, dict):
            all_text += " " + str(act.get("description", ""))
    for act in lesson.get("learner_activities", []):
        if isinstance(act, dict):
            all_text += " " + str(act.get("description", ""))

    for keyword in expensive_keywords:
        if keyword in all_text.lower():
            issues.append(QualityIssue(
                check_name="practical_resources",
                status=QualityStatus.WARN,
                message=f"Lesson assumes '{keyword}' which may not be available in all Ghanaian classrooms.",
                severity="warning",
                category="practicality",
            ))

    if not issues:
        issues.append(QualityIssue(
            check_name="practical_resources",
            status=QualityStatus.PASS,
            message="Resources appear practical for Ghanaian classrooms.",
            category="practicality",
        ))

    # Check class size feasibility
    class_size = lesson.get("class_size", 35)
    if class_size > 60:
        issues.append(QualityIssue(
            check_name="class_size_feasible",
            status=QualityStatus.WARN,
            message=f"Class size of {class_size} may be too large for some activities.",
            severity="warning",
            category="practicality",
        ))
    else:
        issues.append(QualityIssue(
            check_name="class_size_feasible",
            status=QualityStatus.PASS,
            message="Class size is within typical range.",
            category="practicality",
        ))

    return issues


def _check_anti_hallucination(lesson: Dict[str, Any]) -> List[QualityIssue]:
    """Check for invented codes, references, or page numbers."""
    issues = []

    all_text = " ".join([
        str(lesson.get("introduction", "")),
        str(lesson.get("assessment", "")),
        str(lesson.get("conclusion", "")),
        str(lesson.get("homework", "")),
        str(lesson.get("previous_knowledge", "")),
    ])
    for act in lesson.get("main_activities", []):
        if isinstance(act, dict):
            all_text += " " + str(act.get("description", ""))

    # Check for invented page references
    page_pattern = re.compile(r'page\s+\d+', re.IGNORECASE)
    if page_pattern.search(all_text):
        issues.append(QualityIssue(
            check_name="no_invented_references",
            status=QualityStatus.WARN,
            message="Lesson contains page references that may be invented.",
            severity="warning",
            category="anti_hallucination",
        ))
    else:
        issues.append(QualityIssue(
            check_name="no_invented_references",
            status=QualityStatus.PASS,
            message="No invented page references detected.",
            category="anti_hallucination",
        ))

    # Check for invented curriculum codes (codes not from the source indicator)
    source_code = lesson.get("indicator_codes", [""])[0] if lesson.get("indicator_codes") else ""
    code_pattern = re.compile(r'[Bb]\d+\.\d+\.\d+\.\d+')
    found_codes = code_pattern.findall(all_text)
    for code in found_codes:
        if source_code and code != source_code:
            issues.append(QualityIssue(
                check_name="no_invented_codes",
                status=QualityStatus.WARN,
                message=f"Found curriculum code '{code}' in generated text that differs from source '{source_code}'.",
                severity="warning",
                category="anti_hallucination",
            ))
            break

    if not any(i.check_name == "no_invented_codes" for i in issues):
        issues.append(QualityIssue(
            check_name="no_invented_codes",
            status=QualityStatus.PASS,
            message="No invented curriculum codes detected.",
            category="anti_hallucination",
        ))

    return issues


# ── Generation V3 additional checks ───────────────────────────────────────

def _lesson_text(lesson: Dict[str, Any]) -> str:
    """Flatten every teacher-visible text field of a lesson for analysis."""
    # introduction and starter_activity are the same paragraph in deterministic
    # lessons (the builder stores the framing sentence in both fields; the
    # WAPEF/GES renderers dedupe them into ONE phase-1 bullet). Counting both
    # copies here would flag every such lesson as boilerplate — a false
    # positive, not padding.
    intro = str(lesson.get("introduction", ""))
    starter = str(lesson.get("starter_activity", ""))
    parts: List[str] = [
        str(lesson.get("lesson_topic", "")),
        intro,
        "" if starter and starter.strip() == intro.strip() else starter,
        str(lesson.get("assessment", "")),
        str(lesson.get("conclusion", "")),
        str(lesson.get("differentiation", "")),
        str(lesson.get("homework", "")),
        str(lesson.get("previous_knowledge", "")),
    ]
    parts.extend(str(i) for i in lesson.get("indicators", []) or [])
    for key in ("main_activities", "learner_activities", "teacher_activities"):
        for act in lesson.get(key, []) or []:
            if isinstance(act, dict):
                parts.append(str(act.get("description", "")))
            else:
                parts.append(str(act))
    for obj in lesson.get("learning_objectives", []) or []:
        if isinstance(obj, dict):
            parts.append(str(obj.get("description", "")))
        else:
            parts.append(str(obj))
    return " \n ".join(p for p in parts if p)


def _tokens(text: str) -> set:
    return {t for t in re.findall(r"[a-z]{4,}", (text or "").lower())}


def _check_indicator_exactness(lesson: Dict[str, Any], indicator: Indicator) -> List[QualityIssue]:
    """Indicator exactness: the lesson must visibly be about THIS indicator."""
    skill = (indicator.description or indicator.exact_text or "").strip()
    if not skill:
        return [QualityIssue(
            check_name="indicator_exactness", status=QualityStatus.WARN,
            message="No source indicator text available to verify.",
            severity="warning", category="curriculum")]
    try:
        from .lesson_builder import strip_indicator_code
        skill = strip_indicator_code(skill)
    except Exception:
        pass
    tokens = _tokens(skill)
    if not tokens:
        return [QualityIssue(
            check_name="indicator_exactness", status=QualityStatus.PASS,
            message="Indicator is too short to score; treated as addressed.",
            category="curriculum")]
    hay = _tokens(_lesson_text(lesson))
    ratio = len(tokens & hay) / len(tokens)
    if ratio < 0.4:
        return [QualityIssue(
            check_name="indicator_exactness", status=QualityStatus.FAIL,
            message=("Lesson content does not clearly address the uploaded "
                     "indicator (content overlap too low)."),
            severity="error", category="curriculum")]
    return [QualityIssue(
        check_name="indicator_exactness", status=QualityStatus.PASS,
        message="Lesson content is about the uploaded indicator.",
        category="curriculum")]


def _check_subject_appropriateness(lesson: Dict[str, Any]) -> List[QualityIssue]:
    subject = str(lesson.get("subject", "") or "")
    issues: List[QualityIssue] = []
    if not subject:
        return [QualityIssue(
            check_name="subject_appropriateness", status=QualityStatus.WARN,
            message="Lesson has no subject; subject pedagogy cannot be verified.",
            severity="warning", category="pedagogy")]
    try:
        from .pedagogy import profile_for_subject, SUBJECT_TO_PROFILE
        subject_key = _normalize_subject(subject)
        profile = profile_for_subject(subject_key)
        known = subject_key in SUBJECT_TO_PROFILE
    except Exception:
        known, profile = False, None
    if not known:
        issues.append(QualityIssue(
            check_name="subject_appropriateness", status=QualityStatus.WARN,
            message=f"No subject-specific pedagogy profile for '{subject}'.",
            severity="warning", category="pedagogy"))
    else:
        issues.append(QualityIssue(
            check_name="subject_appropriateness", status=QualityStatus.PASS,
            message=f"Subject pedagogy appropriate for {getattr(profile, 'label', subject)}.",
            category="pedagogy"))
    return issues


def _check_class_level_appropriateness(lesson: Dict[str, Any]) -> List[QualityIssue]:
    class_level = str(lesson.get("class_level", "") or "")
    if not class_level or class_level.lower() == "unknown":
        return [QualityIssue(
            check_name="class_level_appropriateness", status=QualityStatus.WARN,
            message="Class level is unknown; appropriateness cannot be verified.",
            severity="warning", category="pedagogy")]
    return [QualityIssue(
        check_name="class_level_appropriateness", status=QualityStatus.PASS,
        message=f"Lesson written for {class_level}.", category="pedagogy")]


def _check_starter_main_plenary_coherence(lesson: Dict[str, Any]) -> List[QualityIssue]:
    """The phases must tell ONE instructional story about the same skill."""
    skill_tokens = _tokens(str(lesson.get("lesson_topic", "")) + " " + " ".join(
        str(i) for i in lesson.get("indicators", []) or []))
    starter = str(lesson.get("starter_activity", lesson.get("introduction", "")))
    plenary = str(lesson.get("conclusion", ""))
    main_text = " ".join(
        str(a.get("description", "")) if isinstance(a, dict) else str(a)
        for a in lesson.get("main_activities", []) or []
    )
    # Coherence signal: the main block should share vocabulary with the lesson
    # topic/indicator. This catches a generic lecture dropped into a lesson
    # whose starter and plenary are about something else.
    if skill_tokens:
        main_overlap = len(skill_tokens & _tokens(main_text)) / max(len(skill_tokens), 1)
    else:
        main_overlap = 1.0
    if not main_text or not starter or not plenary:
        return [QualityIssue(
            check_name="phase_coherence", status=QualityStatus.WARN,
            message="Starter, main and plenary are not all present as a coherent sequence.",
            severity="warning", category="coherence")]
    if main_overlap < 0.25:
        return [QualityIssue(
            check_name="phase_coherence", status=QualityStatus.WARN,
            message="Main activities share little vocabulary with the starter/indicator — phases may not tell one story.",
            severity="warning", category="coherence")]
    return [QualityIssue(
        check_name="phase_coherence", status=QualityStatus.PASS,
        message="Starter, main and plenary form one coherent instructional sequence.",
        category="coherence")]


def _check_assessment_alignment(lesson: Dict[str, Any], indicator: Optional[Indicator]) -> List[QualityIssue]:
    """Assessment must measure the same target learning as the objective."""
    objective_text = " ".join(
        str(o.get("description", "")) if isinstance(o, dict) else str(o)
        for o in lesson.get("learning_objectives", []) or []
    )
    assessment = str(lesson.get("assessment", ""))
    if not assessment:
        return []  # already reported by has_assessment
    obj_tokens = _tokens(objective_text)
    skill_tokens = _tokens((indicator.description if indicator else "") or "")
    target = obj_tokens | skill_tokens
    if target:
        overlap = len(target & _tokens(assessment)) / max(len(target), 1)
        if overlap < 0.2:
            return [QualityIssue(
                check_name="assessment_alignment", status=QualityStatus.WARN,
                message="Assessment wording is only loosely connected to the objective/indicator.",
                severity="warning", category="assessment")]
    return [QualityIssue(
        check_name="assessment_alignment", status=QualityStatus.PASS,
        message="Assessment measures the intended learning.", category="assessment")]


def _check_differentiation_usefulness(lesson: Dict[str, Any]) -> List[QualityIssue]:
    diff = str(lesson.get("differentiation", "") or "").strip()
    if not diff:
        return [QualityIssue(
            check_name="differentiation_usefulness", status=QualityStatus.WARN,
            message="No differentiation provided.",
            severity="warning", category="differentiation")]
    lowered = diff.lower()
    has_support = "support" in lowered or "scaffold" in lowered
    has_extension = "extension" in lowered or "enrich" in lowered or "challenge" in lowered
    if len(diff) < 30 or not (has_support or has_extension):
        return [QualityIssue(
            check_name="differentiation_usefulness", status=QualityStatus.WARN,
            message="Differentiation looks like a token entry with no instructional value.",
            severity="warning", category="differentiation")]
    return [QualityIssue(
        check_name="differentiation_usefulness", status=QualityStatus.PASS,
        message="Differentiation supports the actual activity (support/extension).",
        category="differentiation")]


def _check_cognitive_demand(lesson: Dict[str, Any], indicator: Optional[Indicator]) -> List[QualityIssue]:
    """Flag lessons whose demand drops below the indicator's demand."""
    try:
        from .indicator_interpreter import interpret_indicator
        if indicator is not None:
            interp = interpret_indicator(indicator, indicator.source_subject or "")
            bloom = interp.bloom_level
        else:
            bloom = ""
    except Exception:
        bloom = ""
    if bloom in ("apply", "analyze", "evaluate", "create"):
        text = _lesson_text(lesson).lower()
        higher = [
            "explain", "justify", "solve", "apply", "compare", "analyse",
            "analyze", "create", "design", "evaluate", "investigate",
            "demonstrate", "construct", "produce", "perform", "practise",
            "practice", "measure", "record",
        ]
        if not any(v in text for v in higher):
            return [QualityIssue(
                check_name="cognitive_demand", status=QualityStatus.WARN,
                message=f"Indicator demands '{bloom}' but the lesson activities stay at recall level.",
                severity="warning", category="cognition")]
    return [QualityIssue(
        check_name="cognitive_demand", status=QualityStatus.PASS,
        message="Cognitive demand is appropriate to the indicator.", category="cognition")]


def _check_boilerplate(lesson: Dict[str, Any]) -> List[QualityIssue]:
    """Detect repeated/boilerplate sentences that pad the lesson."""
    text = _lesson_text(lesson)
    sentences = [s.strip().lower() for s in re.split(r"[.!?\n]+", text) if len(s.strip()) > 25]
    if not sentences:
        return []
    counts: Dict[str, int] = {}
    for s in sentences:
        counts[s] = counts.get(s, 0) + 1
    repeated = [s for s, n in counts.items() if n >= 2]
    if repeated:
        return [QualityIssue(
            check_name="boilerplate_detection", status=QualityStatus.WARN,
            message=f"Lesson repeats the same text {len(repeated)} time(s); possible boilerplate.",
            severity="warning", category="quality")]
    return [QualityIssue(
        check_name="boilerplate_detection", status=QualityStatus.PASS,
        message="No repeated boilerplate detected.", category="quality")]


def _check_required_fields(lesson: Dict[str, Any]) -> List[QualityIssue]:
    """Critical missing fields make a lesson unusable and MUST fail."""
    required = {
        "learning_objectives": lesson.get("learning_objectives"),
        "main_activities": lesson.get("main_activities"),
        "assessment": lesson.get("assessment"),
        "conclusion": lesson.get("conclusion"),
        "indicator_codes": lesson.get("indicator_codes"),
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        return [QualityIssue(
            check_name="required_fields", status=QualityStatus.FAIL,
            message=f"Lesson is missing required field(s): {', '.join(missing)}.",
            severity="error", category="quality")]
    return [QualityIssue(
        check_name="required_fields", status=QualityStatus.PASS,
        message="All required fields are present.", category="quality")]


def _check_internal_contradiction(lesson: Dict[str, Any]) -> List[QualityIssue]:
    """Catch self-contradictory lessons (e.g. impossible duration)."""
    duration = lesson.get("duration_minutes", 0) or 0
    if duration <= 0:
        return [QualityIssue(
            check_name="internal_contradiction", status=QualityStatus.FAIL,
            message="Lesson duration is zero or negative.",
            severity="error", category="quality")]
    total_main = sum(
        (a.get("duration_minutes", 0) or 0) if isinstance(a, dict) else 0
        for a in lesson.get("main_activities", []) or []
    )
    if total_main > duration * 1.5:
        return [QualityIssue(
            check_name="internal_contradiction", status=QualityStatus.WARN,
            message="Main activities exceed the lesson duration.",
            severity="warning", category="quality")]
    return [QualityIssue(
        check_name="internal_contradiction", status=QualityStatus.PASS,
        message="No internal contradiction detected.", category="quality")]


def _check_irrelevant_content(lesson: Dict[str, Any]) -> List[QualityIssue]:
    """Detect content that does not belong to this subject/lesson."""
    subject = str(lesson.get("subject", "") or "").lower()
    text = _lesson_text(lesson).lower()
    # A few clear cross-subject contamination markers.
    markers = {
        "mathematics": ["photosynthesis", "volcanic", "poem structure"],
        "science": ["simultaneous equation", "grammar tense"],
        "english language": ["quadratic formula", "photosynthesis"],
    }
    for subj, words in markers.items():
        if subj in subject and any(w in text for w in words):
            return [QualityIssue(
                check_name="irrelevant_content", status=QualityStatus.WARN,
                message=f"Lesson text contains content unrelated to {subject}.",
                severity="warning", category="relevance")]
    return [QualityIssue(
        check_name="irrelevant_content", status=QualityStatus.PASS,
        message="No irrelevant generated content detected.", category="relevance")]


# ── Main Quality Gate ─────────────────────────────────────────────────────

def validate_lesson_quality(
    lesson: Dict[str, Any],
    indicator: Optional[Indicator] = None,
) -> QualityReport:
    """Run the full quality gate on a generated lesson plan.

    Args:
        lesson: The lesson plan as a dictionary.
        indicator: The source curriculum indicator (for curriculum checks).

    Returns:
        QualityReport with pass/warn/fail status and issues.
    """
    report = QualityReport()

    # Run all checks
    all_issues = []

    if indicator:
        all_issues.extend(_check_curriculum_match(lesson, indicator))

    all_issues.extend(_check_objectives(lesson))
    all_issues.extend(_check_activities(lesson))
    all_issues.extend(_check_assessment(lesson))
    all_issues.extend(_check_coherence(lesson))
    all_issues.extend(_check_practicality(lesson))
    all_issues.extend(_check_anti_hallucination(lesson))

    # ── Generation V3 checks (PART T: 17 required checks) ───────────────
    all_issues.extend(_check_required_fields(lesson))
    all_issues.extend(_check_internal_contradiction(lesson))
    all_issues.extend(_check_boilerplate(lesson))
    all_issues.extend(_check_subject_appropriateness(lesson))
    all_issues.extend(_check_class_level_appropriateness(lesson))
    all_issues.extend(_check_starter_main_plenary_coherence(lesson))
    all_issues.extend(_check_assessment_alignment(lesson, indicator))
    all_issues.extend(_check_differentiation_usefulness(lesson))
    all_issues.extend(_check_cognitive_demand(lesson, indicator))
    all_issues.extend(_check_irrelevant_content(lesson))
    if indicator:
        all_issues.extend(_check_indicator_exactness(lesson, indicator))

    report.issues = all_issues

    # Calculate overall status
    has_failures = any(i.status == QualityStatus.FAIL for i in all_issues)
    has_warnings = any(i.status == QualityStatus.WARN for i in all_issues)

    if has_failures:
        report.overall_status = QualityStatus.FAIL
    elif has_warnings:
        report.overall_status = QualityStatus.WARN
    else:
        report.overall_status = QualityStatus.PASS

    # Calculate score (0-100)
    total = len(all_issues)
    passed = sum(1 for i in all_issues if i.status == QualityStatus.PASS)
    warned = sum(1 for i in all_issues if i.status == QualityStatus.WARN)
    failed = sum(1 for i in all_issues if i.status == QualityStatus.FAIL)

    if total > 0:
        report.score = round((passed * 100 + warned * 70) / total, 1)
    else:
        report.score = 0.0

    return report

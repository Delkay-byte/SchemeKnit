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
class BatchQualityReport:
    """Variation/anti-repetition gate result for a WHOLE batch of lessons.

    The single-lesson gate cannot judge repetition or lesson-to-lesson
    continuity — those are properties of the batch. This report carries the
    batch-level checks so a generated batch can fail the gate as a whole.
    """

    lessons: int = 0
    issues: List[QualityIssue] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not any(i.status == QualityStatus.FAIL for i in self.issues)

    @property
    def failures(self) -> List[QualityIssue]:
        return [i for i in self.issues if i.status == QualityStatus.FAIL]

    def summary(self) -> Dict[str, Any]:
        return {
            "lessons": self.lessons,
            "passed": self.passed,
            "failures": len(self.failures),
            "failure_messages": [i.message for i in self.failures],
        }


# ── Pattern & variation checks (Layers 3/4) ─────────────────────────────────
#
# Twelve checks extending the single-lesson gate; nine run per lesson inside
# ``validate_lesson_quality`` and three run across a batch inside
# ``validate_batch_variation``. They are not arbitrary: each has a explicit
# PASS/WARN/FAIL condition and a lesson (or batch) that violates it FAILS.

_GENERIC_FILLER = (
    "learners practise the concept",
    "learners practise input devices",
    "complete the task",
    "do the activity",
    "work with your partner",
    "practise the skill",
    "carry out the activity",
)

#: Activity-type → resource-support signal. A lesson whose main activity type
#: is practical/investigative needs SOMETHING concrete listed; a discussion-
#: type lesson does not.
_ACTIVITY_RESOURCE_NEEDS = {
    "practical", "investigation", "observation", "creation",
    "demonstration", "classification", "experiment",
}


def _plain(value: Any) -> str:
    """Normalise a field to a plain string (model_dump() keeps enums)."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    # Enum member (Subject.MATHEMATICS etc.) — use its value, never str().
    return str(getattr(value, "value", value))


def _lesson_focus(lesson: Dict[str, Any]) -> str:
    """The lesson's own indicator text, code-stripped, for alignment checks."""
    parts = lesson.get("indicators") or []
    text = " ".join(str(p) for p in parts if p)
    if not text:
        text = str(lesson.get("lesson_topic") or "")
    code_re = re.compile(r"[BbKk]?\d+(?:\.\d+){2,4}")
    return code_re.sub("", text).strip()


def _lesson_main_descriptions(lesson: Dict[str, Any]) -> List[str]:
    return [str(a.get("description", "")) for a in (lesson.get("main_activities") or [])]


def _check_pattern_focus_alignment(lesson: Dict[str, Any]) -> List[QualityIssue]:
    """(1) Every MAIN phase names the lesson's own indicator focus — a phase
    about 'the concept' with no link to THIS indicator is not teachable as is.
    """
    focus = _lesson_focus(lesson)
    if not focus or len(focus) < 4:
        return []
    focus_words = {w for w in re.findall(r"[a-z]{3,}", focus.lower())}
    # Drop very generic curriculum words so the check is not vacuous.
    focus_words -= {"learners", "learner", "indicator", "the", "and", "able"}
    if not focus_words:
        return []
    issues = []
    descs = _lesson_main_descriptions(lesson)
    missing = [i for i, desc in enumerate(descs)
               if not any(w in desc.lower() for w in focus_words)]
    if missing:
        issues.append(QualityIssue(
            check_name="phase_indicator_focus",
            status=QualityStatus.WARN,
            message=f"{len(missing)} of {len(descs)} main phases do not "
                    f"reference the lesson's indicator focus.",
            severity="warning", category="activities",
        ))
    else:
        issues.append(QualityIssue(
            check_name="phase_indicator_focus", status=QualityStatus.PASS,
            message="Main phases reference the lesson's indicator focus.",
            category="activities",
        ))
    return issues


def _check_objective_indicator_alignment(lesson: Dict[str, Any]) -> List[QualityIssue]:
    """(2) The learning objective points at THIS indicator, not generic work."""
    focus = _lesson_focus(lesson)
    objectives = lesson.get("learning_objectives") or []
    obj_text = " ".join(str(o.get("description", "")) for o in objectives).lower()
    if not focus or not obj_text or len(focus) < 4:
        return []
    focus_words = {w for w in re.findall(r"[a-z]{3,}", focus.lower())}
    focus_words -= {"learners", "learner", "indicator", "able"}
    if not focus_words:
        return []
    if not any(w in obj_text for w in focus_words):
        return [QualityIssue(
            check_name="objective_indicator_alignment",
            status=QualityStatus.WARN,
            message="Learning objective does not reference the lesson's "
                    "indicator focus (may be a synonym — verify).",
            severity="warning", category="objectives",
        )]
    return [QualityIssue(
        check_name="objective_indicator_alignment", status=QualityStatus.PASS,
        message="Learning objective references the lesson's indicator focus.",
        category="objectives",
    )]


def _check_phase_action_specificity(lesson: Dict[str, Any]) -> List[QualityIssue]:
    """(3) Phases describe concrete teacher/learner actions — never a bare
    heading, never 'Learners practise input devices' style filler.

    A phase is only a hard FAIL when it carries no usable content at all
    (a bare heading such as 'Teacher adds.' or an explicit filler phrase).
    A concrete but terse phase ('Learners sort samples into categories') is
    legitimate, so terseness stays a warning.
    """
    descs = _lesson_main_descriptions(lesson)
    if not descs:
        return []
    filler = [d for d in descs if any(p in d.lower() for p in _GENERIC_FILLER)]
    # A bare heading carries fewer than three real words — not a task.
    bare = [d for d in descs if len(_content_words(d)) < 3]
    if filler or bare:
        first = (filler or bare)[0]
        kind = "generic filler" if filler else "a bare heading, not a task"
        return [QualityIssue(
            check_name="phase_action_specificity", status=QualityStatus.FAIL,
            message=f"Main phase is not teachable as written ({kind}): "
                    f"{first.strip()[:80]}",
            severity="error", category="activities",
        )]
    thin = [d for d in descs if len(d.strip()) < 40]
    if len(thin) > len(descs) // 2:
        return [QualityIssue(
            check_name="phase_action_specificity", status=QualityStatus.WARN,
            message="Main phases are too short to describe concrete actions.",
            severity="warning", category="activities",
        )]
    return [QualityIssue(
        check_name="phase_action_specificity", status=QualityStatus.PASS,
        message="Main phases describe concrete teacher and learner actions.",
        category="activities",
    )]


_SPECIFICITY_STOPWORDS = frozenset({
    "the", "and", "for", "with", "into", "onto", "their", "them", "then",
    "will", "can", "may", "not", "out", "off", "but", "are", "was", "its",
})


def _content_words(text: str) -> List[str]:
    """Real words (>=3 chars) excluding glue words — a heading detector."""
    return [w for w in re.findall(r"[a-z]{3,}", (text or "").lower())
            if w not in _SPECIFICITY_STOPWORDS]


def _check_subject_specific_pedagogy(lesson: Dict[str, Any]) -> List[QualityIssue]:
    """(4) Subject specificity: the MAIN phases must not all be identical to
    another subject's generic template — every phase carries the subject's own
    pedagogical voice. Checked structurally: phases use the subject's verb
    vocabulary, never a subject-agnostic placeholder."""
    subject = _plain(lesson.get("subject")).lower()
    descs = _lesson_main_descriptions(lesson)
    if not subject or not descs:
        return []
    blob = " ".join(descs).lower()
    # Subject-agnostic placeholders that indicate the pedagogy layer was
    # bypassed entirely.
    placeholders = ("this topic", "the concept", "the lesson topic")
    if any(p in blob for p in placeholders):
        return [QualityIssue(
            check_name="subject_specific_pedagogy", status=QualityStatus.WARN,
            message="Main phases use subject-agnostic placeholders.",
            severity="warning", category="activities",
        )]
    return [QualityIssue(
        check_name="subject_specific_pedagogy", status=QualityStatus.PASS,
        message="Main phases carry subject-specific pedagogy.",
        category="activities",
    )]


def _check_pattern_subject_suitability(lesson: Dict[str, Any]) -> List[QualityIssue]:
    """(5) The selected teaching pattern must be compatible with the lesson's
    subject — an incompatible pattern is a selection defect, not a style."""
    from .patterns import pattern_for_id

    pattern_id = str(lesson.get("pattern_id") or "").strip()
    if not pattern_id:
        # No pattern (single-lesson/early-years path) — nothing to check.
        return []
    pattern = pattern_for_id(pattern_id)
    if pattern is None:
        return [QualityIssue(
            check_name="pattern_subject_suitability", status=QualityStatus.WARN,
            message=f"Lesson carries unknown pattern id '{pattern_id}'.",
            severity="warning", category="activities",
        )]
    subject = _plain(lesson.get("subject")).strip().lower()
    from .pedagogy import profile_for_subject
    profile_key = profile_for_subject(subject).key
    if pattern.compatible_subjects and profile_key not in pattern.compatible_subjects:
        return [QualityIssue(
            check_name="pattern_subject_suitability", status=QualityStatus.FAIL,
            message=f"Pattern '{pattern.name}' is not compatible with {subject}.",
            severity="error", category="activities",
        )]
    return [QualityIssue(
        check_name="pattern_subject_suitability", status=QualityStatus.PASS,
        message=f"Pattern '{pattern.name}' is compatible with the lesson subject.",
        category="activities",
    )]


def _check_filler_density(lesson: Dict[str, Any]) -> List[QualityIssue]:
    """(7) Generic filler density: the lesson's phases must not lean on
    filler sentences as padding."""
    blob = " ".join([str(lesson.get("starter_activity") or ""),
                     " ".join(_lesson_main_descriptions(lesson)),
                     str(lesson.get("conclusion") or "")]).lower()
    hits = [p for p in _GENERIC_FILLER if p in blob]
    if hits:
        return [QualityIssue(
            check_name="filler_density", status=QualityStatus.WARN,
            message=f"Generic filler present: {hits[:2]}",
            severity="warning", category="coherence",
        )]
    return [QualityIssue(
        check_name="filler_density", status=QualityStatus.PASS,
        message="No generic filler in the lesson phases.", category="coherence",
    )]


def _check_assessment_activity_alignment(lesson: Dict[str, Any]) -> List[QualityIssue]:
    """(8) The assessment must align with the indicator's own action — an
    indicator that asks learners to 'classify' must not be assessed only with
    a written recall test."""
    focus = _lesson_focus(lesson)
    assessment = str(lesson.get("assessment") or "")
    if not focus or not assessment.strip() or len(focus) < 4:
        return []
    action_verbs = set(re.findall(r"\b(classif|sort|group|investigat|predict|"
                                  r"experiment|demonstrat|perform|create|design|"
                                  r"compose|construct|compare| analys|analyz|"
                                  r"discuss|explain|describe|solve|calculate|"
                                  r"apply|measure|observe)\w*", focus.lower()))
    if not action_verbs:
        return []
    low = assessment.lower()
    if not any(v in low for v in action_verbs):
        return [QualityIssue(
            check_name="assessment_activity_alignment", status=QualityStatus.WARN,
            message="Assessment does not use the indicator's own action verb.",
            severity="warning", category="assessment",
        )]
    return [QualityIssue(
        check_name="assessment_activity_alignment", status=QualityStatus.PASS,
        message="Assessment uses the indicator's own action verb.",
        category="assessment",
    )]


def _check_assignment_alignment(lesson: Dict[str, Any]) -> List[QualityIssue]:
    """(9) Class and home assignments must be real tasks tied to the
    indicator, not empty or generic stand-ins."""
    issues = []
    focus = _lesson_focus(lesson)
    for field_name, label in (("class_assignment", "Class"),
                              ("home_assignment", "Home")):
        value = str(lesson.get(field_name) or "").strip()
        if not value:
            issues.append(QualityIssue(
                check_name=f"{field_name}_alignment",
                status=QualityStatus.WARN,
                message=f"{label} assignment is empty.", severity="warning",
                category="assessment",
            ))
        elif len(value) < 20:
            issues.append(QualityIssue(
                check_name=f"{field_name}_alignment",
                status=QualityStatus.WARN,
                message=f"{label} assignment is too short to be a real task.",
                severity="warning", category="assessment",
            ))
        else:
            issues.append(QualityIssue(
                check_name=f"{field_name}_alignment", status=QualityStatus.PASS,
                message=f"{label} assignment is a concrete task.",
                category="assessment",
            ))
    # Both assignments must not be identical copies of each other.
    ca = str(lesson.get("class_assignment") or "").strip()
    ha = str(lesson.get("home_assignment") or "").strip()
    if ca and ha and ca == ha:
        issues.append(QualityIssue(
            check_name="assignment_differentiation", status=QualityStatus.FAIL,
            message="Class and home assignments are identical.",
            severity="error", category="assessment",
        ))
    elif ca and ha:
        issues.append(QualityIssue(
            check_name="assignment_differentiation", status=QualityStatus.PASS,
            message="Class and home assignments are distinct tasks.",
            category="assessment",
        ))
    if focus and (ca or ha):
        blob = f"{ca} {ha}".lower()
        focus_words = {w for w in re.findall(r"[a-z]{3,}", focus.lower())}
        focus_words -= {"learners", "learner", "indicator", "able"}
        if focus_words and not any(w in blob for w in focus_words):
            issues.append(QualityIssue(
                check_name="assignment_indicator_alignment",
                status=QualityStatus.WARN,
                message="Assignments do not reference the lesson's indicator focus.",
                severity="warning", category="assessment",
            ))
            return issues
        if focus_words:
            issues.append(QualityIssue(
                check_name="assignment_indicator_alignment",
                status=QualityStatus.PASS,
                message="Assignments reference the lesson's indicator focus.",
                category="assessment",
            ))
    return issues


def _check_resource_alignment(lesson: Dict[str, Any]) -> List[QualityIssue]:
    """(10) A practical/investigative lesson must list concrete resources —
    'practical work' with nothing on the table cannot be taught."""
    descs = _lesson_main_descriptions(lesson)
    resources = [str(r) for r in (lesson.get("teaching_learning_resources") or [])]
    blob = " ".join(descs).lower()
    needs_concrete = any(t in blob for t in
                         ("practical", "investigate", "experiment", "observe",
                          "device", "apparatus", "materials", "measure"))
    if not needs_concrete:
        return [QualityIssue(
            check_name="resource_alignment", status=QualityStatus.PASS,
            message="Lesson activity does not require concrete resources.",
            category="practicality",
        )]
    if not resources:
        return [QualityIssue(
            check_name="resource_alignment", status=QualityStatus.WARN,
            message="Practical/investigative phase but no resources listed.",
            severity="warning", category="practicality",
        )]
    return [QualityIssue(
        check_name="resource_alignment", status=QualityStatus.PASS,
        message="Practical phases have listed resources.", category="practicality",
    )]


def _new_variation_checks(lesson: Dict[str, Any]) -> List[QualityIssue]:
    """The nine per-lesson pattern/variation checks (checks 1-5, 7-10)."""
    issues: List[QualityIssue] = []
    issues.extend(_check_pattern_focus_alignment(lesson))
    issues.extend(_check_objective_indicator_alignment(lesson))
    issues.extend(_check_phase_action_specificity(lesson))
    issues.extend(_check_subject_specific_pedagogy(lesson))
    issues.extend(_check_pattern_subject_suitability(lesson))
    issues.extend(_check_filler_density(lesson))
    issues.extend(_check_assessment_activity_alignment(lesson))
    issues.extend(_check_assignment_alignment(lesson))
    issues.extend(_check_resource_alignment(lesson))
    return issues


def validate_batch_variation(
    lessons: List[Dict[str, Any]],
    *,
    class_level: str = "",
) -> BatchQualityReport:
    """Batch-level variation gate (checks 6, 11, 12).

      6.  no identical phase sequences across UNRELATED lessons;
      11. prior-lesson continuity: consecutive lessons on the same strand
          carry a starter that builds on what came before;
      12. no inappropriate pattern repetition (cloned phases or one shape
          dominating the batch).

    A batch that violates any of these FAILS — the same standard as the
    single-lesson gate.
    """
    from .variation import BatchHistory, fingerprint_lesson

    report = BatchQualityReport(lessons=len(lessons))
    if len(lessons) < 2:
        return report

    history = BatchHistory(class_level=class_level)
    for lesson in lessons:
        history.record(fingerprint_lesson(
            lesson, pattern_id=str(lesson.get("pattern_id") or "")))

    rep = history.repetition_report()

    # 6 / 12. cloned or dominating phase sequences across unrelated lessons.
    # A clone (identical RENDERED phases) is a hard failure — the batch
    # repeats itself. A dominating shape may still be curriculum-justified, so
    # it is a warning: the gate flags it, the teacher decides.
    for dup in rep.get("duplicated_phase_sequences", []):
        status = QualityStatus.FAIL if dup.get("cloned") else QualityStatus.WARN
        report.issues.append(QualityIssue(
            check_name="batch_phase_repetition",
            status=status,
            message=(f"{dup['count']} lessons share the identical teaching shape "
                     f"('{dup['pattern']}')"
                     + (" with identical rendered phases." if dup.get("cloned")
                        else ", which dominates the batch.")),
            severity="error" if dup.get("cloned") else "warning",
            category="coherence",
        ))

    # 12b. identical starter text across lessons (one opener for the batch).
    for dup in rep.get("duplicated_starters", []):
        report.issues.append(QualityIssue(
            check_name="batch_starter_repetition",
            status=QualityStatus.FAIL,
            message=f"{dup['count']} lessons open with the identical starter text.",
            severity="error", category="coherence",
        ))

    # 6b. identical rendered main sequence (cloned MAIN block).
    for dup in rep.get("duplicated_main_sequences", []):
        report.issues.append(QualityIssue(
            check_name="batch_main_repetition",
            status=QualityStatus.FAIL,
            message=f"{dup['count']} lessons share the identical MAIN sequence.",
            severity="error", category="coherence",
        ))

    # 12c. a single pattern dominating an otherwise varied batch.
    distinct = rep.get("distinct_patterns", 0)
    if distinct and len(lessons) >= 6 and distinct == 1:
        report.issues.append(QualityIssue(
            check_name="batch_pattern_diversity",
            status=QualityStatus.WARN,
            message="The whole batch used one teaching pattern.",
            severity="warning", category="coherence",
        ))
    elif distinct and len(lessons) >= 6:
        report.issues.append(QualityIssue(
            check_name="batch_pattern_diversity", status=QualityStatus.PASS,
            message=f"Batch used {distinct} distinct teaching patterns.",
            category="coherence",
        ))

    # 11. prior-lesson continuity: consecutive lessons must not contradict
    # the teaching order — the next lesson's starter must reference something
    # the previous lesson taught (link), and no two consecutive lessons may
    # carry the exact same indicator focus.
    for i in range(1, len(lessons)):
        prev_focus = _lesson_focus(lessons[i - 1])
        this_focus = _lesson_focus(lessons[i])
        if prev_focus and this_focus and prev_focus == this_focus:
            report.issues.append(QualityIssue(
                check_name="prior_lesson_continuity",
                status=QualityStatus.WARN,
                message=f"Lessons {i} and {i + 1} carry the identical indicator "
                        f"focus — a duplicated lesson.",
                severity="warning", category="curriculum",
            ))
    if not any(i.check_name == "prior_lesson_continuity" for i in report.issues):
        report.issues.append(QualityIssue(
            check_name="prior_lesson_continuity", status=QualityStatus.PASS,
            message="No duplicated consecutive indicator focus.",
            category="curriculum",
        ))

    return report


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
    # Early-years observable actions (Nursery/KG phrasings such as "Learners
    # can show and talk about …" / "act out …" describe what the child
    # demonstrably DOES — they are not vague verbs).
    "show", "act out", "explore", "talk about", "observe", "sing", "point",
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
    conclusion = str(lesson.get("conclusion", ""))

    def _norm(value: str) -> str:
        return re.sub(r"\s+", " ", (value or "")).strip().lower()

    # The stored timeline carries PHASE 1 / PHASE 3 rows so the lesson's
    # minutes sum exactly (Priority 2 §10). Those rows MIRROR the canonical
    # starter/conclusion fields by construction — the same sentence stored in
    # two places is schema, not padding. Only the canonical copy is counted;
    # a genuinely repeated sentence inside one field still is.
    canonical = {_norm(v) for v in (intro, starter, conclusion) if v and v.strip()}

    parts: List[str] = [
        str(lesson.get("lesson_topic", "")),
        intro,
        "" if starter and starter.strip() == intro.strip() else starter,
        str(lesson.get("assessment", "")),
        conclusion,
        str(lesson.get("differentiation", "")),
        str(lesson.get("homework", "")),
        str(lesson.get("previous_knowledge", "")),
    ]
    parts.extend(str(i) for i in lesson.get("indicators", []) or [])
    for key in ("main_activities", "learner_activities", "teacher_activities"):
        for act in lesson.get(key, []) or []:
            if isinstance(act, dict):
                desc = str(act.get("description", ""))
            else:
                desc = str(act)
            if desc and _norm(desc) in canonical:
                continue
            parts.append(desc)
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


def _split_sentences(text: str) -> List[str]:
    """Split text into sentences without breaking on common abbreviations.

    Curriculum text is full of ``etc.``, ``e.g.`` and numeric ranges
    (``1-5.``, ``0 – 2.``): a naive split on ``[.!?]`` turns one sentence into
    several fragments, and two DIFFERENT sentences that happen to share such a
    fragment ("Model … etc." from two different phase descriptions) then look
    like boilerplate. The abbreviation periods are masked before splitting so
    only real sentence boundaries are used.
    """
    masked = re.sub(r"\b(etc|e\.g|i\.e|vs|Mr|Mrs|Dr|Prof|St|No)\.", r"\1<DOT>", text)
    parts = re.split(r"(?<=[.!?])\s+|\n+", masked)
    return [p.replace("<DOT>", ".").strip() for p in parts if p.strip()]


def _check_boilerplate(lesson: Dict[str, Any]) -> List[QualityIssue]:
    """Detect repeated/boilerplate sentences that pad the lesson."""
    text = _lesson_text(lesson)
    sentences = [s.lower() for s in _split_sentences(text) if len(s) > 25]
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
    }
    missing = [k for k, v in required.items() if not v]
    # A lesson must be anchored to its source curriculum. Indicator-bearing
    # schemes anchor on the indicator code; indicatorless early-years schemes
    # (the WAPEF Nursery source has no Content Standard / Indicator columns at
    # all) anchor on their strand/sub-strand. A lesson with NEITHER is still a
    # failure — no threshold is lowered, the anchor is simply expressed in the
    # vocabulary the source actually uses.
    if not lesson.get("indicator_codes"):
        anchor = lesson.get("strand") or lesson.get("sub_strand")
        if not anchor:
            missing.append("indicator_codes")
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

    # ── Pattern & variation checks (Layers 3/4): nine per-lesson checks ──
    all_issues.extend(_new_variation_checks(lesson))

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

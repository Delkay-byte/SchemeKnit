"""
SchemeKnit Deterministic Lesson Builder (Generation Engine V3)
=============================================================

Builds ONE complete, coherent, subject-aware lesson plan from ONE allocated
indicator. This is the deterministic-first layer: AI is an ENRICHMENT layer on
top and never rewrites the curriculum.

Guarantees:
  * The uploaded indicator remains authoritative. Generated text is visibly
    about the exact indicator — it is quoted into the starter, objectives,
    activities, assessment and plenary.
  * Subject pedagogy differs by subject (mathematics ≠ science ≠ English …).
  * The three phases tell ONE instructional story:
        starter activates prerequisite knowledge
        → teacher introduces/elicits the new concept
        → learners practise the target skill
        → assessment measures that same skill
        → plenary consolidates and links forward.
  * Objectives are learner-centred, observable and measurable, and there is no
    automatic quota of objectives — quantity follows the lesson (one primary
    objective, aligned to the indicator).
  * Resources are realistic for Ghanaian classrooms (no projector/internet/
    laboratory assumptions).
  * Variation is deterministic: subject + indicator activity type + lesson
    position + previous/next context. The same input always yields the same
    baseline lesson.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import List, Optional, Tuple

from ..models import (
    AllocatedIndicator, TermConfig, LessonPlan, LessonStatus, Subject,
    ClassLevel, LearningObjective, TeachingActivity,
)
from .pedagogy import profile_for_subject, SubjectPedagogy

_CODE_RE = re.compile(r"^\s*[Bb]?\d+(?:\.\d+){2,4}[.:]?\s*")

#: Legacy learner-facing prefixes stripped before re-phrasing.
_LEARNER_PREFIXES = (
    "learners can ", "students can ", "pupils can ",
    "learners should be able to ", "students should be able to ",
    "by the end of the lesson, learners should be able to: ",
    "by the end of the lesson, learners should be able to ",
    "by the end of the lesson, the learner should be able to: ",
    "by the end of the lesson, the learner should be able to ",
)


def strip_indicator_code(text: str) -> str:
    """Remove a leading curriculum code (e.g. B7.4.3.1.2) from indicator text."""
    if not text:
        return ""
    return _CODE_RE.sub("", text).strip() or text.strip()


def _learner_phrase(indicator: str) -> str:
    """Phrase the indicator as an approved learner-facing performance statement."""
    clean = strip_indicator_code(indicator)
    lower = clean.lower()
    for prefix in _LEARNER_PREFIXES:
        if lower.startswith(prefix):
            clean = clean[len(prefix):]
            break
    return f"Learners can {clean}".strip()


def _derive_topic(alloc: AllocatedIndicator) -> str:
    parts = [p for p in (alloc.strand, alloc.sub_strand) if p]
    return " - ".join(parts) if parts else "Lesson"


def _safe_format(template: str, **values) -> str:
    """Format a template, substituting empty strings for unknown placeholders."""
    return template.format_map(defaultdict(str, values))


def _distribute(total: int, weights: List[float]) -> List[int]:
    """Split ``total`` minutes across weights, as integers that sum to total."""
    total = max(int(total), 1)
    n = len(weights)
    if n == 0:
        return []
    raw = [w / sum(weights) * total for w in weights]
    out = [int(x) for x in raw]
    remainder = total - sum(out)
    # Hand out the remainder in order of the largest fractional part.
    order = sorted(range(n), key=lambda i: raw[i] - out[i], reverse=True)
    for i in order[:remainder]:
        out[i] += 1
    # Guarantee every phase gets at least one minute.
    for i in range(n):
        if out[i] < 1:
            donor = max(range(n), key=lambda j: out[j])
            if out[donor] > 1:
                out[donor] -= 1
                out[i] += 1
    return out


def _interpret(alloc: AllocatedIndicator, subject: str):
    """Best-effort subject/indicator interpretation (never fatal)."""
    try:
        from .indicator_interpreter import interpret_indicator
        from . import Indicator
        ind = Indicator(
            code=alloc.indicator_code or "",
            exact_text=f"{alloc.indicator_code or ''} {alloc.indicator_description or ''}".strip(),
            description=alloc.indicator_description or "",
            source_week=alloc.week_number,
            source_subject=subject or "",
        )
        return interpret_indicator(ind, subject or "")
    except Exception:
        return None


def build_lesson(
    alloc: AllocatedIndicator,
    config: TermConfig,
    scheme_id: str,
    previous_indicator: Optional[str] = None,
    next_indicator: Optional[str] = None,
) -> LessonPlan:
    """Compose one deterministic, subject-aware, coherent lesson plan."""
    subject_name = (
        config.subject.value if isinstance(config.subject, Subject) else str(config.subject)
    )
    profile: SubjectPedagogy = profile_for_subject(subject_name)

    skill = strip_indicator_code(alloc.indicator_description)
    topic = _derive_topic(alloc)
    class_level = (
        config.class_level.value
        if isinstance(config.class_level, ClassLevel) else str(config.class_level)
    )
    duration = int(config.lesson_duration_minutes or 60)

    prev_short = strip_indicator_code(previous_indicator or "")
    next_short = strip_indicator_code(next_indicator or "")

    fmt = dict(
        skill=skill, topic=topic, strand=alloc.strand or "",
        sub_strand=alloc.sub_strand or "", class_level=class_level,
        prev=prev_short, next=next_short,
        content_standard=alloc.content_standard_description or "",
    )

    # ── STARTER ─────────────────────────────────────────────────────────
    starter = _safe_format(profile.starter_template, **fmt)
    if prev_short:
        starter = f"Build on the previous lesson ('{prev_short}'). " + starter
    intro = starter

    # ── MAIN ────────────────────────────────────────────────────────────
    starter_min = max(5, round(duration * 0.15))
    plenary_min = max(5, round(duration * 0.20))
    main_total = max(duration - starter_min - plenary_min, len(profile.main_phases))
    phase_minutes = _distribute(main_total, [p.weight for p in profile.main_phases])

    main_activities: List[TeachingActivity] = []
    learner_activities: List[TeachingActivity] = []
    teacher_activities: List[TeachingActivity] = []
    for phase, minutes in zip(profile.main_phases, phase_minutes):
        desc = _safe_format(phase.template, **fmt)
        main_activities.append(TeachingActivity(
            phase=phase.name.upper(), description=desc,
            duration_minutes=minutes, resources=[],
        ))
        learner_activities.append(TeachingActivity(
            phase="LEARNER",
            description=_learner_task(phase.name, skill),
            duration_minutes=minutes, resources=[],
        ))
        teacher_activities.append(TeachingActivity(
            phase="TEACHER",
            description=_teacher_move(phase.name, skill),
            duration_minutes=minutes, resources=[],
        ))

    # ── ASSESSMENT (measures the same target skill) ─────────────────────
    assessment = _safe_format(profile.assessment_template, **fmt)

    # ── PLENARY ─────────────────────────────────────────────────────────
    conclusion = _safe_format(profile.plenary_template, **fmt)
    if next_short:
        conclusion += f" Preview the next lesson ('{next_short}')."

    # ── Differentiation (tied to the actual activity) ───────────────────
    differentiation = "\n".join([
        f"Support: {_safe_format(profile.support_template, **fmt)}",
        f"Extension: {_safe_format(profile.extension_template, **fmt)}",
        f"Grouping: {profile.grouping}",
    ])

    # ── Resources: subject-realistic + teacher-supplied (never fabricated) ─
    resources: List[str] = []
    for r in list(profile.resources) + list(getattr(config, "teaching_learning_resources", []) or []):
        r = (r or "").strip()
        if r and r not in resources:
            resources.append(r)

    keywords: List[str] = []
    for k in list(profile.keywords) + list(getattr(config, "keywords", []) or []):
        k = (k or "").strip()
        if k and k not in keywords:
            keywords.append(k)

    objectives = [LearningObjective(
        description=_learner_phrase(alloc.indicator_description),
        indicator_code=alloc.indicator_code,
    )]

    previous_knowledge = (
        f"Previous lesson: {prev_short}" if prev_short
        else "Learners' everyday experience related to this activity."
    )

    return LessonPlan(
        scheme_of_work_id=scheme_id,
        term_config_id=config.id,
        week_number=alloc.week_number,
        teaching_week=alloc.teaching_week or alloc.week_number,
        carry_forward=bool(alloc.carry_forward),
        lesson_sequence=0,  # assigned by the caller (curriculum order)
        lesson_date=alloc.lesson_date or config.term_start_date,
        lesson_number=alloc.period_index,
        period="",  # caller sets the period label
        class_level=config.class_level,
        subject=config.subject,
        class_size=config.class_size,
        duration_minutes=duration,
        school_name=config.school_name,
        teacher_name=config.teacher_name,
        strand=alloc.strand,
        sub_strand=alloc.sub_strand,
        content_standard=alloc.content_standard_description,
        content_standard_code=alloc.content_standard_code,
        indicators=[alloc.indicator_description],
        indicator_codes=[alloc.indicator_code],
        lesson_topic=topic,
        essential_questions=[profile.essential_question],
        previous_knowledge=previous_knowledge,
        keywords=keywords,
        learning_objectives=objectives,
        core_competencies=list(getattr(config, "core_competencies", []) or []),
        teaching_learning_resources=resources,
        introduction=intro,
        starter_activity=starter,
        main_activities=main_activities,
        learner_activities=learner_activities,
        teacher_activities=teacher_activities,
        assessment=assessment,
        differentiation=differentiation,
        conclusion=conclusion,
        references=list(getattr(config, "references", []) or []),
        status=LessonStatus.GENERATED,
        ai_generated=False,
    )


def _learner_task(phase_name: str, skill: str) -> str:
    name = (phase_name or "").lower()
    if "demonstrat" in name or "model" in name or "explanation" in name or "teaching" in name:
        return f"Watch and listen carefully, then describe each step of {skill} in your own words."
    if "guided" in name or "observation" in name or "practice" in name or "discussion" in name:
        return f"Work with your partner/group to carry out the task for {skill} and record what you find."
    if "independent" in name or "application" in name or "challenge" in name or "creation" in name or "try" in name:
        return f"Complete the task for {skill} on your own and check your work before you finish."
    if "critique" in name or "reflection" in name:
        return f"Look at your work on {skill}, decide what went well and what to improve."
    return f"Take an active part in the activity for {skill}."


def _teacher_move(phase_name: str, skill: str) -> str:
    name = (phase_name or "").lower()
    if "demonstrat" in name or "model" in name or "explanation" in name or "teaching" in name:
        return f"Model {skill} slowly, think aloud, and check that all learners can see and hear."
    if "guided" in name or "observation" in name or "practice" in name or "discussion" in name:
        return f"Move around the room, observe each group, and correct misconceptions about {skill} on the spot."
    if "independent" in name or "application" in name or "challenge" in name or "creation" in name or "try" in name:
        return f"Circulate, give brief individual feedback, and note learners who need re-teaching of {skill}."
    if "critique" in name or "reflection" in name:
        return f"Lead a short, kind critique and highlight good examples relating to {skill}."
    return f"Facilitate the activity and keep every learner focused on {skill}."

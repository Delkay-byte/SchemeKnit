"""Pedagogical quality and teacher-voice guards for whole-lesson Zeli output.

Teacher-authored voice is a generation rule, not a styling pass. This module
keeps teacher actions, learner actions and curriculum metadata separate so a
learner description is never rewritten as an instruction and a curriculum label
is never mistaken for a teaching mistake.

No provider vocabulary, model id, key or secret is exposed by these helpers.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

#: Fourth-person narration of the teacher's work. Learner actions never carry
#: these openers, so a direct instruction stays distinct from an observer's
#: report about the teacher.
_THIRD_PERSON_OPENERS = re.compile(
    r"^\s*(?:the\s+|a\s+)?(?:teacher|facilitator|instructor|educator)\b",
    re.IGNORECASE,
)
_THIRD_PERSON_MID = re.compile(
    r"\b(?:by|for|of)\s+the\s+(?:teacher|facilitator|instructor|educator)\s+"
    r"(?:goes?|moves?|asks?|writes?|shows?|demonstrates?|explains?|gives?|"
    r"guides?|helps?|checks?|marks?|observes?|points?|prepares?|provides?|"
    r"records?|reminds?|repeats?|sets?|states?|summarises?|summarizes?|"
    r"supports?|tells?|works?|is|will|should|must|can)\b",
    re.IGNORECASE,
)
_THIRD_PERSON_FUTURE = re.compile(
    r"\b(?:teacher|facilitator)\s+(?:will|should|must|can)\b",
    re.IGNORECASE,
)
# The teacher as the SUBJECT of an action anywhere in instructional prose.
# "Learners listen to the teacher" is a learner action and stays untouched.
_THIRD_PERSON_SUBJECT = re.compile(
    r"\b(?:the\s+)?(?:teacher|facilitator|instructor|educator)\s+"
    r"(?:goes?|moves?|asks?|writes?|shows?|demonstrates?|explains?|gives?|"
    r"guides?|helps?|checks?|marks?|observes?|points?|prepares?|provides?|"
    r"records?|reminds?|repeats?|sets?|states?|summarises?|summarizes?|"
    r"supports?|tells?|works?|is|will|should|must|can)\b",
    re.IGNORECASE,
)
_PASSIVE_DIRECTION = re.compile(
    r"\b(?:learners|pupils|students)\s+"
    r"(?:are|is|will\s+be|should\s+be)\s+"
    r"(?:expected\s+to\s+be\s+)?"
    r"(?:guided|shown|given|asked|told|helped|provided|required)\b",
    re.IGNORECASE,
)

#: Resources that break the low-resource Ghanaian classroom contract even when
#: a kit happens to list them. A named local object is never flagged here.
_UNSUITABLE_RESOURCE = re.compile(
    r"\b(?:projector|smartboard|internet|wifi|laptop|desktop\s+computer|"
    r"tablet|smartphone|photocop(?:y|ies)|printed\s+worksheets?)\b",
    re.IGNORECASE,
)
_GENERIC_RUBRIC_LABEL = re.compile(
    r"^(?:meets\s+(?:the\s+)?(?:stated\s+)?criteria(?:\s+of\s+the\s+task)?|"
    r"criteria\s+not\s+yet\s+met|all\s+(?:stated\s+)?criteria\s+met|"
    r"most\s+criteria\s+met|use\s+of\s+the\s+agreed\s+criteria|"
    r"presentation\s+and\s+completeness|originality\s*/\s*purposeful\s+"
    r"modification|explanation\s+of\s+the\s+design/work)$",
    re.IGNORECASE,
)

_PREFIX = re.compile(
    r"^\s*(?:the\s+)?(?:teacher|facilitator|instructor|educator)\s+",
    re.IGNORECASE,
)
_REQUIRED_TO = re.compile(r"^is\s+required\s+to\s+", re.IGNORECASE)

#: Ordered: longer phrases first so they win over single-verb substitutions.
_PHRASE_MAP = (
    (re.compile(r"^go(?:es|es round|round|around)\s+(?:round\s+|around\s+)?"
                r"(?:checking|monitoring|supervising)\b", re.IGNORECASE),
     "Move around the classroom and check"),
    (re.compile(r"^moves?\s+(?:around|round)\s+to\s+support\b", re.IGNORECASE),
     "Move around the classroom and support"),
    (re.compile(r"^moves?\s+(?:around|round)\s+(?:checking|monitoring)\b",
                re.IGNORECASE),
     "Move around the classroom and check"),
    (re.compile(r"^works?\s+through\b", re.IGNORECASE), "Work through"),
    (re.compile(r"^goes\s+round\b", re.IGNORECASE),
     "Move around the classroom"),
)

_VERB_MAP = {
    "asks": "Ask",
    "arranges": "Arrange",
    "checks": "Check",
    "collects": "Collect",
    "concludes": "Conclude",
    "demonstrates": "Demonstrate",
    "displays": "Display",
    "explains": "Explain",
    "gives": "Give",
    "guides": "Guide",
    "helps": "Help",
    "marks": "Mark",
    "moves": "Move",
    "observes": "Observe",
    "points": "Point",
    "practises": "Practise",
    "prepares": "Prepare",
    "provides": "Provide",
    "records": "Record",
    "reminds": "Remind",
    "repeats": "Repeat",
    "sets": "Set",
    "shows": "Show",
    "states": "State",
    "summarises": "Summarise",
    "summarizes": "Summarize",
    "supports": "Support",
    "tells": "Tell",
    "uses": "Use",
    "writes": "Write",
}

_TEACHER_ACTION_PATHS = (
    ("starter",),
    ("plenary",),
)
_TEACHER_ACTION_FIELD = "teacher_action"


def third_person_teacher_narration(text: Any) -> bool:
    """Return True when ``text`` reports what the teacher does instead of
    telling the teacher what to do.

    Learner-action prose (``Learners identify ...``) and direct instructions
    (``Write 246 ...``) are deliberately not flagged.
    """
    value = str(text or "").strip()
    if not value:
        return False
    return bool(
        _THIRD_PERSON_OPENERS.search(value)
        or _THIRD_PERSON_MID.search(value)
        or _THIRD_PERSON_FUTURE.search(value)
        or _THIRD_PERSON_SUBJECT.search(value)
    )


def passive_teacher_direction(text: Any) -> bool:
    """Return True for passive directions that hide who must act."""
    return bool(_PASSIVE_DIRECTION.search(str(text or "")))


def zeli_teacher_voice(text: Any) -> str:
    """Convert third-person teacher narration to a direct classroom command.

    Only teacher-action text is passed here. The transformation is conservative:
    when no teacher subject is present the original wording is returned, so
    learner activities and curriculum facts are never rewritten.
    """
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if not value:
        return ""

    had_prefix = bool(_PREFIX.match(value))
    if had_prefix:
        value = _PREFIX.sub("", value, count=1).strip()
        value = _REQUIRED_TO.sub("", value, count=1).strip()
    else:
        # Mid-sentence teacher references cannot be converted safely without
        # disturbing learner activities; leave them for validation to reject.
        if _THIRD_PERSON_MID.search(value) or _THIRD_PERSON_FUTURE.search(value):
            return value
        return value

    if not value:
        return ""

    for pattern, replacement in _PHRASE_MAP:
        new_value, count = pattern.subn(replacement, value, count=1)
        if count:
            value = new_value
            break

    first, _, rest = value.partition(" ")
    folded = first.lower().rstrip(".,;:")
    replacement = _VERB_MAP.get(folded)
    if replacement is not None:
        tail = rest
        value = f"{replacement} {tail}".strip()

    value = value[:1].upper() + value[1:] if value else value
    return value


def normalize_zeli_teacher_voice(content: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of ``content`` with teacher-action fields normalised.

    Learner actions, curriculum identity and all teacher-owned configuration
    are returned untouched.
    """
    if not isinstance(content, dict):
        return content
    result: Dict[str, Any] = dict(content)

    for section in _TEACHER_ACTION_PATHS:
        block = result.get(section[0])
        if isinstance(block, dict):
            action = block.get(_TEACHER_ACTION_FIELD)
            if action:
                updated = dict(block)
                updated[_TEACHER_ACTION_FIELD] = zeli_teacher_voice(action)
                result[section[0]] = updated

    main = result.get("main_learning")
    if isinstance(main, dict):
        updated_main = {}
        for key, phase in main.items():
            if isinstance(phase, dict) and phase.get(_TEACHER_ACTION_FIELD):
                updated = dict(phase)
                updated[_TEACHER_ACTION_FIELD] = zeli_teacher_voice(
                    phase[_TEACHER_ACTION_FIELD])
                updated_main[key] = updated
            else:
                updated_main[key] = phase
        result["main_learning"] = updated_main
    elif isinstance(main, list):
        updated_main_list = []
        for phase in main:
            if isinstance(phase, dict) and phase.get(_TEACHER_ACTION_FIELD):
                updated = dict(phase)
                updated[_TEACHER_ACTION_FIELD] = zeli_teacher_voice(
                    phase[_TEACHER_ACTION_FIELD])
                updated_main_list.append(updated)
            else:
                updated_main_list.append(phase)
        result["main_learning"] = updated_main_list

    return result


def _instructional_strings(content: Dict[str, Any]) -> Iterable[str]:
    """Yield instructional prose only: teacher actions and learning activities.

    Metadata such as ``lesson_identity`` and teacher-owned configuration is
    excluded so a curriculum label in metadata is never treated as repetition.
    """
    for section in ("starter", "plenary"):
        block = content.get(section)
        if isinstance(block, dict):
            for field in ("activity", "teacher_action"):
                yield str(block.get(field) or "")

    main = content.get("main_learning")
    phases: List[Any]
    if isinstance(main, dict):
        phases = [value for value in main.values() if isinstance(value, dict)]
    elif isinstance(main, list):
        phases = [value for value in main if isinstance(value, dict)]
    else:
        phases = []
    for phase in phases:
        for field in ("name", "activity", "teacher_action"):
            yield str(phase.get(field) or "")

    assessment = content.get("assessment")
    if isinstance(assessment, dict):
        for field in ("method", "activity", "success_criteria"):
            yield str(assessment.get(field) or "")
    else:
        yield str(assessment or "")

    yield str(content.get("class_assignment") or "")

    differentiation = content.get("differentiation")
    if isinstance(differentiation, dict):
        for value in differentiation.values():
            yield str(value or "")


def _activity_strings(content: Dict[str, Any]) -> Iterable[str]:
    """Yield the substantive teaching tasks, not short teacher commands."""
    for section in ("starter", "plenary"):
        block = content.get(section)
        if isinstance(block, dict):
            yield str(block.get("activity") or "")
    main = content.get("main_learning")
    phases: List[Any]
    if isinstance(main, dict):
        phases = [value for value in main.values() if isinstance(value, dict)]
    elif isinstance(main, list):
        phases = [value for value in main if isinstance(value, dict)]
    else:
        phases = []
    for phase in phases:
        yield str(phase.get("activity") or "")
    assessment = content.get("assessment")
    if isinstance(assessment, dict):
        yield str(assessment.get("activity") or "")
    else:
        yield str(assessment or "")
    yield str(content.get("class_assignment") or "")


def _teacher_action_strings(content: Dict[str, Any]) -> Iterable[str]:
    for section in ("starter", "plenary"):
        block = content.get(section)
        if isinstance(block, dict):
            yield str(block.get(_TEACHER_ACTION_FIELD) or "")
    main = content.get("main_learning")
    phases: List[Any]
    if isinstance(main, dict):
        phases = [value for value in main.values() if isinstance(value, dict)]
    elif isinstance(main, list):
        phases = [value for value in main if isinstance(value, dict)]
    else:
        phases = []
    for phase in phases:
        yield str(phase.get(_TEACHER_ACTION_FIELD) or "")


def _declared_resource_strings(content: Dict[str, Any]) -> List[str]:
    """Resources the provider explicitly attached to this lesson."""
    values: List[str] = []
    block = content.get("resources")
    if isinstance(block, dict):
        for key in ("source_resources", "suggested_alternatives"):
            values.extend(str(v or "").strip()
                          for v in (block.get(key) or [])
                          if str(v or "").strip())
    elif isinstance(block, list):
        values.extend(str(v or "").strip() for v in block if str(v or "").strip())

    main = content.get("main_learning")
    phases: List[Any]
    if isinstance(main, dict):
        phases = [value for value in main.values() if isinstance(value, dict)]
    elif isinstance(main, list):
        phases = [value for value in main if isinstance(value, dict)]
    else:
        phases = []
    for phase in phases:
        values.extend(str(v or "").strip()
                      for v in (phase.get("resources_used") or [])
                      if str(v or "").strip())
    return values


def _rubric_parts(rubric: Any) -> List[str]:
    """Criterion and descriptor text from dict or model rubrics."""
    parts: List[str] = []
    task = rubric.get("task") if isinstance(rubric, dict) else getattr(
        rubric, "task", "")
    if task:
        parts.append(str(task))
    criteria = rubric.get("criteria") if isinstance(rubric, dict) else getattr(
        rubric, "criteria", None)
    for criterion in criteria or []:
        if isinstance(criterion, dict):
            label = criterion.get("criterion", "")
            descriptors = criterion.get("descriptors") or []
        else:
            label = getattr(criterion, "criterion", "")
            descriptors = getattr(criterion, "descriptors", None) or []
        if label:
            parts.append(str(label))
        for descriptor in descriptors:
            if isinstance(descriptor, dict):
                text = descriptor.get("descriptor", "")
            else:
                text = getattr(descriptor, "descriptor", "")
            if text:
                parts.append(str(text))
    return parts


_FOCUS_STOPWORDS = frozenset({
    "learners", "learner", "teacher", "lesson", "about", "from",
    "with", "into", "that", "this", "their", "them", "then", "when", "which",
    "shows", "show", "describe", "describes", "understand", "understanding",
    "using", "used", "work", "works", "write", "writes", "state", "states",
})


def focus_terms_from_text(text: Any) -> List[str]:
    """Content words used to check that a rubric names the actual task."""
    words = re.findall(r"[A-Za-z]{4,}", str(text or "").lower())
    seen: List[str] = []
    for word in words:
        if word in _FOCUS_STOPWORDS or word in seen:
            continue
        seen.append(word)
        if len(seen) == 12:
            break
    return seen


def generic_rubric_detected(rubric: Any,
                            focus_terms: Optional[Sequence[str]] = None) -> bool:
    """Return True when a rubric only repeats task-neutral band labels.

    A saved rubric is allowed to use the standard four bands. It must still name
    the lesson's task or focus somewhere; otherwise the scoring grid is theatre.
    """
    parts = _rubric_parts(rubric)
    criteria = rubric.get("criteria") if isinstance(rubric, dict) else getattr(
        rubric, "criteria", None)
    if not parts or not criteria:
        return False
    focus = [str(term).strip().lower() for term in (focus_terms or [])
             if len(str(term).strip()) >= 4]
    if focus:
        joined = " ".join(parts).lower()
        if any(term in joined for term in focus):
            return False
    labels: List[str] = []
    for criterion in criteria:
        if isinstance(criterion, dict):
            labels.append(str(criterion.get("criterion") or "").strip())
        else:
            labels.append(str(getattr(criterion, "criterion", "") or "").strip())
    return bool(labels) and all(
        not label or bool(_GENERIC_RUBRIC_LABEL.match(label))
        for label in labels
    )


def lesson_content_fingerprint(content: Dict[str, Any]) -> str:
    """Stable fingerprint of ONE lesson's substantive teaching content.

    Curriculum labels and teacher configuration are excluded. Two lessons for
    different indicators that share this fingerprint did not get distinct
    plans, whatever their codes say.
    """
    parts: List[str] = []
    for section in ("starter", "plenary"):
        block = content.get(section)
        if isinstance(block, dict):
            for field in ("activity", "teacher_action", "learner_action"):
                parts.append(str(block.get(field) or ""))

    main = content.get("main_learning")
    phases: List[Any]
    if isinstance(main, dict):
        phases = [value for value in main.values() if isinstance(value, dict)]
    elif isinstance(main, list):
        phases = [value for value in main if isinstance(value, dict)]
    else:
        phases = []
    for phase in phases:
        for field in ("name", "activity", "teacher_action", "learner_action"):
            parts.append(str(phase.get(field) or ""))

    assessment = content.get("assessment")
    if isinstance(assessment, dict):
        for field in ("method", "activity", "success_criteria"):
            parts.append(str(assessment.get(field) or ""))
    else:
        parts.append(str(assessment or ""))

    worked = content.get("worked_example")
    if isinstance(worked, dict):
        parts.extend(str(worked.get(field) or "")
                     for field in ("problem", "answer", "reasoning"))
        parts.extend(str(step or "") for step in (worked.get("steps") or []))

    for question in content.get("practice_questions") or []:
        if isinstance(question, dict):
            parts.extend(str(question.get(field) or "")
                         for field in ("question", "expected_answer", "reasoning"))

    for item in content.get("assessment_items") or []:
        if isinstance(item, dict):
            parts.extend(str(item.get(field) or "")
                         for field in ("prompt", "expected_evidence",
                                       "marking_guidance"))

    parts.append(str(content.get("class_assignment") or ""))
    differentiation = content.get("differentiation")
    if isinstance(differentiation, dict):
        parts.extend(str(value or "") for value in differentiation.values())

    return re.sub(r"\s+", " ", " ".join(parts)).strip().lower()


def _phase_minutes(content: Dict[str, Any]) -> List[int]:
    values: List[int] = []
    for section in ("starter", "plenary"):
        block = content.get(section)
        if isinstance(block, dict):
            try:
                values.append(int(block.get("duration_minutes") or 0))
            except (TypeError, ValueError):
                values.append(0)
    assessment = content.get("assessment")
    if isinstance(assessment, dict):
        try:
            values.append(int(assessment.get("duration_minutes") or 0))
        except (TypeError, ValueError):
            values.append(0)
    main = content.get("main_learning")
    phases: List[Any]
    if isinstance(main, dict):
        phases = [value for value in main.values() if isinstance(value, dict)]
    elif isinstance(main, list):
        phases = [value for value in main if isinstance(value, dict)]
    else:
        phases = []
    for phase in phases:
        try:
            values.append(int(phase.get("duration_minutes") or 0))
        except (TypeError, ValueError):
            values.append(0)
    return values


#: Teacher-safe wording for internal quality codes. Never expose raw codes,
#: provider details or file paths to the teacher.
QUALITY_FAILURE_MESSAGES = {
    "third_person_teacher_voice": "teacher moments written in third person",
    "passive_teacher_direction": "passive directions with no clear teacher action",
    "missing_worked_example": "a worked example with steps, answer and reasoning",
    "missing_practice_questions": "practice questions",
    "missing_expected_answers": "answers and reasoning for practice questions",
    "missing_marking_guidance": "marking guidance for assessment items",
    "missing_phase_durations": "realistic minutes for every lesson phase",
    "timing_mismatch": "phase minutes that add up to the configured period",
    "sub_strand_repetition": "teaching content instead of a repeated curriculum label",
    "generic_activity": "activities with actual teaching content",
    "missing_resource_guidance": "low-cost local resource preparation and use",
    "unrelated_resource": "resources that belong to this lesson",
    "generic_rubric": "a rubric tied to this task",
}


def quality_failure_summary(codes: Iterable[str]) -> str:
    """Return one human-readable clause for the given internal failure codes."""
    labels = [QUALITY_FAILURE_MESSAGES.get(code, code) for code in codes]
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels[:-1]) + f" and {labels[-1]}"


def validate_zeli_quality(
    content: Any,
    *,
    sub_strand: str = "",
    duration_minutes: int = 0,
    allowed_resources: Optional[Sequence[str]] = None,
    rubric: Any = None,
    focus_terms: Optional[Sequence[str]] = None,
) -> List[str]:
    """Return stable failure codes for poor Zeli content.

    The codes are internal diagnostics only; callers map them to teacher-safe
    messages. An empty list means the payload satisfies the generation rule.
    """
    if not isinstance(content, dict):
        return ["not_an_object"]

    failures: List[str] = []

    instructional = list(_instructional_strings(content))
    if any(third_person_teacher_narration(value) for value in instructional):
        failures.append("third_person_teacher_voice")
    if any(passive_teacher_direction(value) for value in instructional):
        failures.append("passive_teacher_direction")

    worked = content.get("worked_example")
    if not isinstance(worked, dict) or not all(
        str(worked.get(field) or "").strip()
        for field in ("problem", "steps", "answer", "reasoning")
    ):
        failures.append("missing_worked_example")

    questions = content.get("practice_questions")
    if not isinstance(questions, list) or not [
        item for item in questions if isinstance(item, dict) and item
    ]:
        failures.append("missing_practice_questions")
    else:
        if any(
            not str(item.get("expected_answer") or "").strip()
            or not str(item.get("reasoning") or "").strip()
            for item in questions if isinstance(item, dict)
        ):
            failures.append("missing_expected_answers")

    items = content.get("assessment_items")
    if not isinstance(items, list) or not [
        item for item in items if isinstance(item, dict) and item
    ] or any(
        not str(item.get("marking_guidance") or "").strip()
        for item in items if isinstance(item, dict)
    ):
        failures.append("missing_marking_guidance")

    minutes = _phase_minutes(content)
    if not minutes or any(value <= 0 for value in minutes):
        failures.append("missing_phase_durations")
    elif duration_minutes and sum(minutes) != int(duration_minutes):
        failures.append("timing_mismatch")

    prose = [value for value in _instructional_strings(content) if value.strip()]
    label = str(sub_strand or "").strip()
    if label and (len(label.split()) >= 3 or len(label) >= 20):
        occurrences = sum(
            value.lower().count(label.lower()) for value in prose
        )
        if occurrences > 1:
            failures.append("sub_strand_repetition")

    if any(len(value.strip().split()) < 6
           for value in _activity_strings(content) if value.strip()):
        failures.append("generic_activity")

    guidance = content.get("resource_guidance")
    # The output contract allows an empty no_cost_alternative when no substitute
    # is needed. Requiring it would reject a provider that followed the schema.
    if not isinstance(guidance, dict) or not all(
        str(guidance.get(field) or "").strip()
        for field in ("preparation", "use")
    ):
        failures.append("missing_resource_guidance")

    if allowed_resources is not None:
        declared = _declared_resource_strings(content)
        if any(_UNSUITABLE_RESOURCE.search(value) for value in declared):
            failures.append("unrelated_resource")
        else:
            approved = {
                " ".join(str(item or "").split()).lower()
                for item in allowed_resources
                if str(item or "").strip()
            }
            resources_block = content.get("resources")
            if isinstance(resources_block, dict):
                for value in resources_block.get("source_resources") or []:
                    text = " ".join(str(value or "").split()).lower()
                    if text and text not in approved:
                        failures.append("unrelated_resource")
                        break

    if rubric is not None and generic_rubric_detected(rubric, focus_terms):
        failures.append("generic_rubric")

    return failures

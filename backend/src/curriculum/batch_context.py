"""
SchemeKnit Batch Context — Layers 1–4 wiring for one lesson in a batch
======================================================================

This module is where the four generation layers meet for ONE lesson inside a
batch generation run:

    Curriculum Evidence (Layer 1)   → what the official curriculum says
    Subject Pedagogy  (Layer 2)     → how THIS subject teaches that
    Pattern Selection (Layer 3)     → which teaching sequence fits best
    Variation         (Layer 4)     → what has already been used this batch

It is deliberately separate from the lesson builder so the layers stay
distinct in code (no one giant prompt / no one giant function) and so a
future RAG retrieval provider can feed richer evidence into
:func:`select_pattern_for_alloc` without touching the lesson engine.

Contract honoured here:
  * the teacher's scheme remains authoritative for week, sequence, topic and
    resources — evidence only guides the pedagogical interpretation;
  * curriculum fit always outweighs novelty;
  * selection is fully deterministic (same inputs ⇒ same pattern);
  * empty evidence is a valid state: the subject pedagogy carries the lesson.
"""

from __future__ import annotations

import re
from typing import Any, Optional, Set, Tuple

from ..models import AllocatedIndicator, TermConfig
from .evidence import (
    CurriculumEvidence, EvidenceRequest, evidence_for_lesson,
    request_from_lesson,
)
from .patterns import (
    LessonPattern, SelectionContext, novelty_penalty, select_pattern,
)
from .pedagogy import profile_for_subject
from .variation import BatchHistory

#: Very high-frequency structural words, ignored when comparing the scheme's
#: own prose against a corpus record's learning focus.
_FOCUS_STOPWORDS = {
    "the", "and", "for", "with", "are", "was", "were", "has", "have", "not",
    "but", "from", "into", "this", "that", "they", "them", "their", "about",
    "learners", "learner", "use", "using", "able", "can", "how", "what",
    "when", "why", "who", "all", "any", "one", "two", "three", "basic",
    "week", "term", "lesson", "level", "strand", "indicator", "standard",
}


def subject_profile_key(config: TermConfig) -> str:
    """Profile key for the lesson's subject, with KG/Nursery override.

    Mirrors the lesson builder's own override so pattern selection and lesson
    rendering agree on which pedagogy applies.
    """
    from ..models import Subject, ClassLevel
    class_level = (
        config.class_level.value
        if isinstance(config.class_level, ClassLevel) else str(config.class_level)
    )
    if class_level in ("KG 1", "KG 2"):
        return "early_childhood"
    if class_level in ("Nursery", "Nursery 1", "Nursery 2"):
        return "nursery"
    subject_name = (
        config.subject.value if isinstance(config.subject, Subject) else str(config.subject)
    )
    return profile_for_subject(subject_name).key


def build_batch_history(config: TermConfig, scheme_id: str) -> BatchHistory:
    """Create the batch-scoped lesson-generation history (Layer 4).

    Provenance is scheme + subject + class + term so history never leaks
    across schemes or classes and an empty batch starts clean.
    """
    from ..models import ClassLevel, Subject
    class_level = (
        config.class_level.value
        if isinstance(config.class_level, ClassLevel) else str(config.class_level)
    )
    subject = (
        config.subject.value if isinstance(config.subject, Subject) else str(config.subject)
    )
    return BatchHistory(
        scheme_id=scheme_id or "",
        subject=subject,
        class_level=class_level,
        term=getattr(config, "term", "") or "",
    )


def _evidence_focus_aligns(indicator_text: str, evidence: Any) -> bool:
    """Source-authority check on a code-keyed evidence record.

    Schools legitimately renumber indicators (``B7.1.1.1.1`` may be "Place
    value up to one billion" in the official corpus but "Add whole numbers" in
    a school's own scheme). The teacher's scheme is authoritative for WHAT the
    lesson teaches, so a corpus record whose learning focus shares nothing with
    the scheme's prose is treated as *not applicable* to THIS lesson's pattern
    selection — its verbs describe different work.

    Empty states stay permissive (they are valid, not errors):

    * no scheme prose (code-only row)   → evidence IS the authority → aligned
    * no learning focus / focus terms   → nothing to contradict     → aligned
    """
    if evidence is None:
        return False
    prose = (indicator_text or "").strip()
    if not prose:
        return True
    focus_bits = [evidence.learning_focus or ""] + list(
        getattr(evidence, "focus_terms", None) or [])
    focus = " ".join(b for b in focus_bits if b).strip()
    if not focus:
        return True
    shared = _content_words(prose) & _content_words(focus)
    return bool(shared)


def _content_words(text: str) -> set:
    """Content-word set for focus comparison (stopwords and short tokens out)."""
    return {
        w for w in re.findall(r"[a-z]+", (text or "").lower())
        if len(w) > 2 and w not in _FOCUS_STOPWORDS
    }


def build_selection_context(
    alloc: AllocatedIndicator,
    config: TermConfig,
    history: BatchHistory,
    objective_text: str = "",
    previous_indicator: Optional[str] = None,
    evidence: Optional[CurriculumEvidence] = None,
) -> SelectionContext:
    """Assemble the curriculum context for one lesson's pattern selection.

    Layers are kept distinct: Layer 1 evidence is retrieved when not supplied,
    Layer 2 supplies the subject profile, Layer 4 supplies the recent-pattern
    history. Nothing here mutates the allocation — the teacher's scheme stays
    authoritative.
    """
    subject_key = subject_profile_key(config)
    from ..models import ClassLevel
    class_level = (
        config.class_level.value
        if isinstance(config.class_level, ClassLevel) else str(config.class_level)
    )

    # Layer 1 — official curriculum evidence (may legitimately be absent).
    if evidence is None:
        request = request_from_lesson(alloc, subject=config.subject.value
                                      if hasattr(config.subject, "value")
                                      else str(config.subject))
        try:
            evidence = evidence_for_lesson(request)
        except Exception:
            evidence = None

    # The indicator description may carry the source code (D5); select on the
    # readable text so verbs compare cleanly.
    try:
        from .lesson_builder import strip_indicator_code
        indicator_text = strip_indicator_code(
            alloc.indicator_description or "")
    except Exception:
        indicator_text = alloc.indicator_description or ""

    # Source-authority gate: a code-keyed corpus record whose focus does not
    # match the scheme's own prose describes different work — its verbs must
    # not steer this lesson's pedagogy. Code-only rows keep the evidence as
    # their authority.
    evidence_applicable = _evidence_focus_aligns(indicator_text, evidence)
    evidence_verbs: Tuple[str, ...] = tuple(
        evidence.curriculum_action_verbs or []
    ) if (evidence is not None and evidence_applicable) else ()
    evidence_patterns: Tuple[str, ...] = tuple(
        (evidence.exemplar_activity_patterns or [])
        + (evidence.assessment_patterns or [])
    ) if (evidence is not None and evidence_applicable) else ()

    # ── Determine the indicator's activity type (Layer 2 signal) ─────────
    # Same interpretation the builder uses, so selection and rendering agree.
    indicator_activity = ""
    try:
        from .lesson_builder import _interpret, _activity_key
        subject_name = (config.subject.value if hasattr(config.subject, "value")
                        else str(config.subject))
        interp = _interpret(alloc, subject_name)
        indicator_activity = _activity_key(
            interp, alloc.indicator_description or "") or ""
    except Exception:
        indicator_activity = ""

    return SelectionContext(
        subject_profile=subject_key,
        class_level=class_level,
        indicator_text=indicator_text,
        indicator_activity=indicator_activity,
        objective_text=objective_text,
        duration_minutes=int(getattr(config, "lesson_duration_minutes", 60) or 60),
        class_size=int(getattr(config, "class_size", 0) or 0),
        evidence_verbs=evidence_verbs,
        evidence_activity_patterns=evidence_patterns,
        source_resources=tuple(
            str(r) for r in (getattr(alloc, "source_resources", None) or [])),
        lesson_position=len(history.fingerprints),
        recent_pattern_ids=history.recent_pattern_ids(),
        previous_indicator=previous_indicator or "",
    )


def select_pattern_for_alloc(
    alloc: AllocatedIndicator,
    config: TermConfig,
    history: BatchHistory,
    objective_text: str = "",
    previous_indicator: Optional[str] = None,
) -> Optional[LessonPattern]:
    """Select the best-fitting teaching pattern for ONE allocated indicator.

    Returns ``None`` only when the catalog is unavailable — never on a
    curriculum mismatch (the subject's canonical pattern then applies).

    Deterministic: identical inputs always yield the identical pattern. When
    the indicators of a batch genuinely differ, the bounded novelty term
    rotates between equally-fitting patterns; when a demonstration is the
    right method several lessons in a row, it stays selected.

    Early years (Nursery/KG) opt OUT: their pedagogy is play-based and already
    varies by teaching position (see ``_compose_main_phases``), and the 14
    patterns are written/discussion sequences for Basic 1-9. Applying them to
    KG would replace play phases with board work — developmentally wrong.
    """
    if subject_profile_key(config) in _EARLY_YEARS_PROFILES:
        return None

    ctx = build_selection_context(
        alloc, config, history,
        objective_text=objective_text,
        previous_indicator=previous_indicator,
    )
    penalty = novelty_penalty(ctx)
    pattern, _fit, _adj = select_pattern(ctx, novelty_penalty=penalty)
    return pattern


#: Profiles whose pedagogy is play-based early-years development. The 14
#: teaching patterns are written/discussion sequences for Basic 1-9; Nursery
#: and KG already have their own position-varied play pedagogy, so the pattern
#: engine must not engage for them.
_EARLY_YEARS_PROFILES = frozenset({"nursery", "early_childhood", "kg"})

__all__ = [
    "subject_profile_key", "build_batch_history", "build_selection_context",
    "select_pattern_for_alloc",
]

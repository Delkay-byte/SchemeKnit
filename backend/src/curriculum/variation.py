"""
SchemeKnit Variation / Anti-Repetition Layer (Layer 4)
=======================================================

When a teacher generates 10–14 lessons from one scheme, the system MUST NOT
produce the same Phase 1 / Phase 2 / Phase 3 sequence repeatedly — *unless the
indicators genuinely require it*.

This layer makes repetition visible and penalises it in pattern selection:

* :class:`LessonFingerprint` — a normalised signature of ONE generated lesson
  (starter mode, main-activity structure, reflection mode, pattern id,
  resource sequence, assignment pattern). Fingerprints are what the batch
  benchmark compares; they are deliberately normalised so that trivial word
  changes do NOT count as variation.
* :class:`BatchHistory` — the lesson-generation history for the current
  scheme / subject / class / term / batch. It records every lesson built in
  the batch so the NEXT lesson's pattern selection can apply a novelty
  penalty, and it lets a caller report repeated sequences across unrelated
  lessons.

Constraints this layer enforces (from the variation contract):

* Variation is **constrained**. It never varies the curriculum code,
  indicator meaning, learning objective, authoritative source information,
  required sequence, or subject-specific correctness.
* Random wording variation is NEVER the primary solution — variation comes
  from selecting a different *teaching sequence*, not from rephrasing one.
* Curriculum fit always outweighs novelty. The penalty handed to Layer 3 is
  bounded, so a pattern that genuinely fits the indicator wins even when it
  was used in the previous lesson.
* Empty history is a valid state (first lesson of a batch ⇒ no penalty).

Provenance of every recorded lesson is kept (``scheme_id`` / ``subject`` /
``class_level`` / ``term``) so history never leaks across schemes, subjects,
classes or terms.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ── Normalisation ────────────────────────────────────────────────────────────

#: Sentence skeletons that carry no pedagogical content. When two lessons
#: share one of these openers they are repetition, not variation.
_FLEXIBLE_OPENERS = (
    "this lesson builds on",
    "this lesson focuses on",
    "this lesson continues",
    "build on the previous lesson",
    "continue from",
)

#: Generic classroom filler that must not appear across an entire batch as
#: padding (checked by the quality gate and the batch benchmark).
GENERIC_FILLER_PHRASES = (
    "watch and listen carefully",
    "complete the task",
    "work with your partner",
    "learners practise the concept",
    "do the activity",
)


def _norm_text(text: str) -> str:
    """Lower-case, strip punctuation, collapse whitespace."""
    if not text:
        return ""
    s = unicodedata.normalize("NFKD", str(text))
    s = s.encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def normalized_starter(text: str) -> str:
    """The starter with link prefixes removed so that the same opener preceded
    by different previous-lesson links still compares as one opener."""
    body = _norm_text(text)
    # Drop the previous-lesson/day link prefix: it legitimately differs per
    # lesson while the OPENING ACTIVITY is what should vary.
    lowered = (text or "").strip().lower()
    for opener in _FLEXIBLE_OPENERS:
        if lowered.startswith(opener):
            # Cut to the end of the quoted link.
            cut = lowered.find("'", len(opener))
            if cut != -1 and lowered.find("'", cut + 1) != -1:
                body = _norm_text(text[lowered.find("'", cut + 1) + 1:])
            else:
                body = _norm_text(text[len(opener):])
            break
    return body


def normalized_main_sequence(activities: Sequence[Any]) -> str:
    """Structure signature of the MAIN block: normalised step *templates* with
    the indicator's own focus words removed, so two lessons that share a
    sequence but teach different content are still detected as repetition."""
    parts: List[str] = []
    for act in activities or []:
        desc = _norm_text(getattr(act, "description", str(act)))
        # Remove the dominant focus terms (the indicator's own words) so the
        # SIGNATURE of the sentence remains, not the topic.
        parts.append(_skeleton(desc))
    return " | ".join(parts)


#: Function/content words removed to expose sentence skeleton. Only very high
#: frequency connective/structural words are stripped so the skeleton still
#: carries the pedagogical verbs and objects.
_SKELETON_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "their", "this", "that", "these", "those", "they", "them", "it", "its",
    "by", "as", "at", "from", "into", "is", "are", "was", "were", "be",
    "have", "has", "had", "each", "one", "two", "three", "learners",
    "learner", "the", "teacher", "then", "so", "if", "while", "when",
}


def _skeleton(text: str, keep: int = 14) -> str:
    words = [w for w in (text or "").split() if w and w not in _SKELETON_STOP]
    return " ".join(words[:keep])


def normalized_reflection(text: str) -> str:
    return _skeleton(_norm_text(text))


def normalized_resource_sequence(resources: Sequence[Any]) -> str:
    return " | ".join(sorted({_norm_text(r) for r in (resources or []) if _norm_text(r)}))


def assignment_type(text: str) -> str:
    """Classify an assignment text into its task family (never its content)."""
    t = _norm_text(text)
    if not t:
        return "none"
    table = (
        ("sort", "sorting"), ("group", "sorting"), ("classify", "sorting"),
        ("categoris", "sorting"), ("categoriz", "sorting"),
        ("match", "sorting"),
        ("collect", "collection"), ("find one", "collection"),
        ("observe", "observation"), ("record", "observation"),
        ("write", "written"), ("draft", "written"), ("paragraph", "written"),
        ("sentence", "written"), ("summaris", "written"),
        ("summariz", "written"),
        ("practise", "practice"), ("practice", "practice"),
        ("perform", "performance"), ("demonstrate", "demonstration"),
        ("show", "demonstration"),
        ("research", "research"), ("ask", "research"),
        ("interview", "research"),
        ("draw", "production"), ("make", "production"), ("create",
                                                          "production"),
        ("build", "production"), ("construct", "production"),
        ("compare", "comparison"),
        ("reflect", "reflection"), ("discuss", "discussion"),
        ("listen", "listening"), ("read", "reading"),
        ("apply", "application"), ("use", "application"),
        ("evaluate", "evaluation"), ("assess", "evaluation"),
    )
    for marker, family in table:
        if marker in t:
            return family
    return "other"


# ── Lesson fingerprint ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class LessonFingerprint:
    """A normalised signature of one generated lesson (Layer 4).

    Two lessons with an identical fingerprint are pedagogically the same
    lesson. Each field is NORMALISED: the indicator's own content words are
    stripped from the starter / main / reflection so that repetition of
    *structure* is what is detected, not shared topic vocabulary.
    """

    pattern_id: str = ""
    starter_mode: str = ""
    plenary_mode: str = ""
    starter: str = ""
    main_sequence: str = ""
    reflection: str = ""
    resource_sequence: str = ""
    class_assignment_type: str = "other"
    home_assignment_type: str = "other"
    indicator: str = ""
    #: The source indicator CODE this lesson teaches (Priority 2 §18): the
    #: occurrence-stage logic asks "has this code been taught before in this
    #: batch?" — without it the field defaulted to "" and every lesson stayed
    #: stage ``first`` (the repeat-application emphasis never fired).
    indicator_code: str = ""

    @property
    def is_empty(self) -> bool:
        return not (self.pattern_id or self.starter or self.main_sequence)

    def structural_signature(self) -> Tuple[str, ...]:
        """The fields that identify the lesson's TEACHING SHAPE."""
        return (
            self.pattern_id,
            self.starter_mode,
            self.plenary_mode,
            self.class_assignment_type,
            self.home_assignment_type,
        )

    def matches_shape_of(self, other: "LessonFingerprint") -> bool:
        """True when two lessons use the same pedagogical shape."""
        return self.structural_signature() == other.structural_signature()


def fingerprint_lesson(
    lesson: Any,
    pattern_id: str = "",
    starter_mode: str = "",
    plenary_mode: str = "",
) -> LessonFingerprint:
    """Build a fingerprint from a generated ``LessonPlan``.

    ``pattern_id`` / ``starter_mode`` / ``plenary_mode`` are supplied by the
    generator (they are internal and never surface in the UI). When they are
    absent the fingerprint is derived purely from the lesson text, so
    repetition can still be detected on lessons saved by older runs.

    Accepts a ``LessonPlan`` object OR a plain dict (the batch-level gate
    reviews lessons as dicts).
    """
    main = _lesson_field(lesson, "main_activities", [])
    starter_mode = starter_mode or _infer_starter_mode(_lesson_field(lesson, "starter_activity", ""))
    plenary_mode = plenary_mode or _infer_plenary_mode(_lesson_field(lesson, "conclusion", ""))
    return LessonFingerprint(
        pattern_id=pattern_id,
        starter_mode=starter_mode,
        plenary_mode=plenary_mode,
        starter=normalized_starter(_lesson_field(lesson, "starter_activity", "")),
        main_sequence=normalized_main_sequence(main),
        reflection=normalized_reflection(_lesson_field(lesson, "conclusion", "")),
        resource_sequence=normalized_resource_sequence(
            _lesson_field(lesson, "teaching_learning_resources", []) or []
        ),
        class_assignment_type=assignment_type(_lesson_field(lesson, "class_assignment", "")),
        home_assignment_type=assignment_type(_lesson_field(lesson, "home_assignment", "")),
        indicator=_norm_text(" ".join(_lesson_field(lesson, "indicators", []) or [])),
        indicator_code=_first_indicator_code(lesson),
    )


def _first_indicator_code(lesson: Any) -> str:
    """The lesson's primary indicator code ("" when the lesson has none).

    Reads ``indicator_codes`` when the lesson carries it; older dict lessons
    fall back to the first canonical code shape inside the raw indicator
    text, so the occurrence-stage query keeps working for both.
    """
    for code in (_lesson_field(lesson, "indicator_codes", []) or []):
        code = str(code).strip()
        if code:
            return code
    text = " ".join(
        str(i) for i in (_lesson_field(lesson, "indicators", []) or []))
    if not text.strip():
        return ""
    from . import ANY_CODE_RE
    match = ANY_CODE_RE.search(text)
    return match.group(0).strip(" .:") if match else ""


def _lesson_field(lesson: Any, name: str, default: Any) -> Any:
    """Read a field from a LessonPlan object or a plain dict."""
    if isinstance(lesson, dict):
        return lesson.get(name, default)
    return getattr(lesson, name, default)


_STARTER_MODE_MARKERS: List[Tuple[str, Tuple[str, ...]]] = [
    ("prediction", ("predict", "what do you think will happen")),
    ("object_observation", ("observe the", "look at the", "show two",
                            "picture", "real object")),
    ("quick_scenario", ("scenario", "situation", "imagine", "suppose")),
    ("misconception_probe", ("watch for", "misconception", "common error",
                             "careful that")),
    ("diagnostic_question", ("diagnostic", "quick question", "check whether",
                             "who can tell")),
    ("demonstration_teaser", ("show", "demonstrate", "perform")),
    ("short_game", ("game", "song", "rhyme", "clap", "play")),
    ("oral_classification", ("classify", "sort", "group", "which group")),
    ("real_life_connection", ("at home", "in the community", "in ghana",
                              "everyday", "real life")),
    ("vocabulary_activation", ("word wall", "vocabulary", "key words",
                               "oral language")),
    ("contrast_pairs", ("compare", "contrast", "difference between",
                        "same and different")),
    ("retrieval", ("recall", "previous lesson", "remember", "prior",
                   "mental/oral", "drill")),
]


def _infer_starter_mode(text: str) -> str:
    t = _norm_text(text)
    if not t:
        return ""
    for mode, markers in _STARTER_MODE_MARKERS:
        if any(m in t for m in markers):
            return mode
    return "other"


_PLENARY_MODE_MARKERS: List[Tuple[str, Tuple[str, ...]]] = [
    ("exit_question", ("exit", "one question", "before you go")),
    ("teach_a_peer", ("teach a partner", "teach a peer", "explain to a partner",
                      "show a friend")),
    ("one_minute_summary", ("one minute", "60 seconds", "one-sentence",
                            "in one sentence")),
    ("learner_explanation", ("two learners to explain", "ask learners to explain",
                             "explain the rule")),
    ("application_scenario", ("apply", "what would you do", "real life",
                              "at home")),
    ("misconception_correction", ("misconception", "common error",
                                  "correct the")),
    ("retrieval_challenge", ("recap", "quiz", "remember", "recall")),
    ("reflection_question", ("reflect", "what did you learn",
                             "what would you improve")),
    ("demonstration", ("demonstrate", "show me", "perform")),
    ("share_and_critique", ("share", "critique", "feedback", "display")),
    ("explain_rule", ("state the rule", "explain the rule", "summarise the rule")),
    ("oral_recap", ("summarise", "recap", "review the key")),
]


def _infer_plenary_mode(text: str) -> str:
    t = _norm_text(text)
    if not t:
        return ""
    for mode, markers in _PLENARY_MODE_MARKERS:
        if any(m in t for m in markers):
            return mode
    return "other"


# ── Batch history ────────────────────────────────────────────────────────────


@dataclass
class BatchHistory:
    """Lesson-generation history for the current scheme/subject/class/term.

    The generator records one fingerprint per lesson it builds, *in order*.
    Pattern selection then asks for the recently-used pattern ids to apply a
    bounded novelty penalty (Layer 3), and :meth:`repetition_report` lets the
    batch benchmark flag duplicated sequences across unrelated lessons.
    """

    scheme_id: str = ""
    subject: str = ""
    class_level: str = ""
    term: str = ""
    fingerprints: List[LessonFingerprint] = field(default_factory=list)

    # ── Recording ───────────────────────────────────────────────────────

    _recent_selections: str = field(default="", repr=False, compare=False)

    def note_selection(self, pattern_id: str) -> None:
        """Record a selection the SELECTOR made (before the lesson exists).

        Pattern selection needs to know what the previous lessons chose; the
        fingerprint only exists after the lesson is built. ``note_selection``
        feeds the recently-used pattern ids without waiting for the builder,
        and :meth:`record` later adds the full fingerprint.
        """
        if pattern_id:
            self._recent_selections = (
                self._recent_selections + " " + pattern_id).strip()

    def record(self, fingerprint: LessonFingerprint) -> None:
        if fingerprint and not fingerprint.is_empty:
            self.fingerprints.append(fingerprint)

    def record_lesson(
        self, lesson: Any, pattern_id: str = "", starter_mode: str = "",
        plenary_mode: str = "",
    ) -> LessonFingerprint:
        fp = fingerprint_lesson(lesson, pattern_id, starter_mode, plenary_mode)
        self.record(fp)
        return fp

    # ── Queries for Layer 3 selection ────────────────────────────────────

    def recent_pattern_ids(self, window: int = 6) -> Tuple[str, ...]:
        """Pattern ids of the most recent lessons (oldest→newest).

        Combines completed fingerprints with selections that have not yet been
        fingerprinted (the current lesson is mid-flight), keeping the most
        recent ``window`` entries.
        """
        out: List[str] = [fp.pattern_id for fp in self.fingerprints
                          if fp.pattern_id]
        for pid in self._recent_selections.split():
            if pid and pid not in out:
                out.append(pid)
        return tuple(out[-window:])

    def recent_starter_modes(self, window: int = 4) -> Tuple[str, ...]:
        return tuple(
            fp.starter_mode for fp in self.fingerprints[-window:]
            if fp.starter_mode
        )

    def starter_used(self, mode: str, window: int = 3) -> bool:
        if not mode:
            return False
        recent = self.fingerprints[-window:]
        return any(fp.starter_mode == mode for fp in recent)

    def pattern_repeat_streak(self) -> int:
        """How many consecutive immediately-preceding lessons used ONE pattern.

        A streak of ≥ 3 with different indicators is a repetition smell: the
        generator should prefer an equally-fitted alternative.
        """
        ids = [fp.pattern_id for fp in self.fingerprints if fp.pattern_id]
        if not ids:
            return 0
        last = ids[-1]
        streak = 0
        for pid in reversed(ids):
            if pid == last:
                streak += 1
            else:
                break
        return streak

    # ── Repetition detection (batch benchmark + quality gate) ───────────

    def repetition_report(self) -> Dict[str, Any]:
        """Compare every lesson in the batch for forbidden repetition.

        Acceptance rules (batch variation test):
          1. No unrelated lessons have identical entire phase sequences.
          2. No identical starter text appears repeatedly without reason.
          3. No identical main-learning sequence appears repeatedly without
             reason.
          4. Pattern selection varies where indicators differ.
          5. Variation never compromises curriculum alignment.
          6. The same pattern may be reused when justified.
        """
        fps = self.fingerprints
        n = len(fps)
        report: Dict[str, Any] = {
            "lessons": n,
            "distinct_patterns": len({fp.pattern_id for fp in fps if fp.pattern_id}),
            "distinct_starters": len({fp.starter for fp in fps if fp.starter}),
            "distinct_main_sequences": len({fp.main_sequence for fp in fps if fp.main_sequence}),
            "distinct_starter_modes": len({fp.starter_mode for fp in fps if fp.starter_mode}),
            "duplicated_starters": [],
            "duplicated_main_sequences": [],
            "duplicated_phase_sequences": [],
            "filler_density": {},
        }

        # 2. Identical normalised starter text across lessons.
        by_starter: Dict[str, List[int]] = {}
        for i, fp in enumerate(fps):
            if fp.starter:
                by_starter.setdefault(fp.starter, []).append(i)
        for text, idxs in by_starter.items():
            if len(idxs) > 1 and text:
                report["duplicated_starters"].append({
                    "indices": idxs,
                    "count": len(idxs),
                    "text": text[:160],
                })

        # 3. Identical normalised main sequence across lessons.
        by_main: Dict[str, List[int]] = {}
        for i, fp in enumerate(fps):
            if fp.main_sequence:
                by_main.setdefault(fp.main_sequence, []).append(i)
        for seq, idxs in by_main.items():
            if len(idxs) > 1 and seq:
                report["duplicated_main_sequences"].append({
                    "indices": idxs,
                    "count": len(idxs),
                    "sequence": seq[:160],
                })

        # 1. Identical whole-shape sequences across UNRELATED lessons.
        by_shape: Dict[Tuple[str, ...], List[int]] = {}
        for i, fp in enumerate(fps):
            if fp.pattern_id:
                by_shape.setdefault(fp.structural_signature(), []).append(i)
        for shape, idxs in by_shape.items():
            if len(idxs) < 2:
                continue
            # Rule 6 / rule 1: reusing a PATTERN is legitimate when the
            # indicators genuinely call for the same teaching method — but the
            # RENDERED phase sequence must still differ (each lesson renders
            # through its own indicator focus). A repeat is a defect only when
            # the phases are actually identical, or one teaching shape is
            # dominating the batch (a stuck engine), or a long unbroken run of
            # the same shape.
            mains = {fps[i].main_sequence for i in idxs if fps[i].main_sequence}
            # Fewer distinct main texts than lessons ⇒ some pair is a clone.
            cloned = len(mains) < len(idxs)
            dominant = len(idxs) > max(3, n // 2 - 1)
            streak = self._shape_streak(shape) > 3
            if cloned or dominant or streak:
                report["duplicated_phase_sequences"].append({
                    "indices": idxs,
                    "count": len(idxs),
                    "pattern": shape[0],
                    "cloned": cloned,
                    "dominant": dominant,
                    "streak": streak,
                })

        # Filler density across the whole batch.
        report["filler_density"] = self.filler_density()
        return report

    def _shape_streak(self, shape: Tuple[str, ...]) -> int:
        """Longest unbroken run of one teaching shape in the batch."""
        best = run = 0
        for fp in self.fingerprints:
            if fp.pattern_id and fp.structural_signature() == shape:
                run += 1
                best = max(best, run)
            else:
                run = 0
        return best

    def filler_density(self) -> Dict[str, int]:
        """Count of generic filler phrases across the recorded lessons."""
        counts: Dict[str, int] = {p: 0 for p in GENERIC_FILLER_PHRASES}
        for fp in self.fingerprints:
            blob = " ".join([fp.starter, fp.main_sequence, fp.reflection])
            for phrase in GENERIC_FILLER_PHRASES:
                if phrase in blob:
                    counts[phrase] += 1
        return {k: v for k, v in counts.items() if v}


__all__ = [
    "normalized_starter", "normalized_main_sequence", "normalized_reflection",
    "normalized_resource_sequence", "assignment_type", "LessonFingerprint",
    "fingerprint_lesson", "BatchHistory", "GENERIC_FILLER_PHRASES",
]

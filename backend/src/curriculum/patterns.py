"""
SchemeKnit Lesson Pattern Catalog (Layer 3)
=============================================

A bounded set of pedagogical LESSON PATTERNS. A pattern is NOT a script and
NOT a prompt — it is a **teaching sequence**: an ordered set of phase roles
(STARTER → MAIN steps → PLENARY) together with the curriculum metadata that
says WHEN that sequence is the right one to teach with.

Patterns are selected from curriculum fit (Layer 1 evidence + Layer 2 subject
pedagogy + the indicator's own activity type), NEVER at random. Curriculum
alignment always outweighs novelty: if a demonstration is genuinely the right
method three lessons in a row, a demonstration pattern may be selected three
times in a row. Variation (Layer 4) only breaks ties among *equally fitted*
patterns — it never drags in an unsuitable pattern merely to appear different.

Each pattern declares (per the pattern-selection contract):
  * ``compatible_subjects``      — profile keys the pattern suits (empty = all)
  * ``suitable_verbs``           — curriculum action verbs that signal fit
  * ``suitable_activity_types``  — indicator activity-type keys (see
                                   ``indicator_interpreter.ACTIVITY_KEYWORDS``)
  * ``suitable_assessment_forms``— assessment forms the pattern produces
  * ``suitable_levels``          — class-level bands (empty = all bands)
  * ``min_duration``/``max_duration`` — minutes the sequence needs
  * ``resource_needs``           — LOW / MEDIUM resource weight
  * ``unsuitable_when``          — situations in which the pattern is a poor fit
  * ``steps``                    — the ordered MAIN phase roles
  * ``starter_mode``/``plenary_mode`` — variation hooks used by Layer 4

The catalog is pure DATA; the lesson builder renders the selected pattern
through the subject-pedagogy templates so one pattern still reads differently
in Mathematics, Computing and RME.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

# ── Level bands ──────────────────────────────────────────────────────────────

NURSERY_BAND = "nursery"
KG_BAND = "kg"
LOWER_BAND = "basic_lower"      # Basic 1–3
UPPER_BAND = "basic_upper"      # Basic 4–6
JHS_BAND = "jhs"                # Basic 7–9
SHS_BAND = "shs"


def level_band(class_level: str) -> str:
    """Map a class-level label onto its curriculum band."""
    text = " ".join((class_level or "").split()).lower()
    if not text or text == "unknown":
        return ""
    if "nursery" in text:
        return NURSERY_BAND
    if text.startswith("kg"):
        return KG_BAND
    for n in ("1", "2", "3"):
        if text.endswith(f"basic {n}") or text == f"basic {n}":
            return LOWER_BAND
    for n in ("4", "5", "6"):
        if text.endswith(f"basic {n}") or text == f"basic {n}":
            return UPPER_BAND
    for n in ("7", "8", "9"):
        if text.endswith(f"basic {n}") or text == f"basic {n}":
            return JHS_BAND
    if "shs" in text or "senior" in text:
        return SHS_BAND
    if "basic" in text:
        return UPPER_BAND
    return ""


# ── Pattern shapes ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PatternStep:
    """One MAIN phase inside a pattern.

    ``role`` is one of ``input`` (teacher presents), ``guided`` (scaffolded
    learner work), ``independent`` (learner works alone) or ``synthesis``
    (consolidation). ``activity_key`` selects the shared activity bank the
    builder renders this step from, and ``use_indicator_activity`` marks steps
    that must instead follow the INDICATOR's own activity type (so a
    procedural indicator is still taught procedurally inside any pattern).
    """

    name: str
    role: str
    activity_key: str
    use_indicator_activity: bool = False


@dataclass(frozen=True)
class LessonPattern:
    id: str
    name: str
    description: str
    steps: List[PatternStep]
    compatible_subjects: Set[str] = field(default_factory=set)
    suitable_verbs: Set[str] = field(default_factory=set)
    suitable_activity_types: Set[str] = field(default_factory=set)
    suitable_assessment_forms: Set[str] = field(default_factory=set)
    suitable_levels: Set[str] = field(default_factory=set)
    min_duration: int = 30
    max_duration: int = 120
    resource_needs: str = "LOW"           # LOW | MEDIUM
    unsuitable_when: Tuple[str, ...] = ()
    starter_mode: str = "retrieval"
    plenary_mode: str = "oral_recap"

    def fingerprint_structure(self) -> Tuple[str, ...]:
        """Structural signature used for repetition detection (Layer 4)."""
        return (self.id,) + tuple(s.role for s in self.steps)


def _p(
    pid: str, name: str, description: str, steps: List[PatternStep],
    subjects: Sequence[str] = (), verbs: Sequence[str] = (),
    activities: Sequence[str] = (), assessments: Sequence[str] = (),
    levels: Sequence[str] = (), duration: Tuple[int, int] = (30, 120),
    resources: str = "LOW", unsuitable: Tuple[str, ...] = (),
    starter: str = "retrieval", plenary: str = "oral_recap",
) -> LessonPattern:
    return LessonPattern(
        id=pid, name=name, description=description, steps=steps,
        compatible_subjects=set(subjects), suitable_verbs=set(verbs),
        suitable_activity_types=set(activities),
        suitable_assessment_forms=set(assessments), suitable_levels=set(levels),
        min_duration=duration[0], max_duration=duration[1],
        resource_needs=resources, unsuitable_when=unsuitable,
        starter_mode=starter, plenary_mode=plenary,
    )


# ── The bounded pattern catalog (14 teaching sequences) ─────────────────────
#
# Selection metadata is deliberately conservative: a pattern only advertises
# the verbs/activities/subjects it genuinely serves, so the scorer's fit term
# (not its novelty term) decides.

PATTERNS: List[LessonPattern] = [
    # 1 — OBSERVE → CLASSIFY → EXPLAIN
    _p(
        "observe_classify_explain", "Observe → Classify → Explain",
        "Learners study concrete examples, group them by an observable rule, "
        "then explain the rule — the natural shape for identifying and "
        "sorting new categories.",
        [
            PatternStep("Observe", "input", "observation"),
            PatternStep("Classify", "guided", "classification", True),
            PatternStep("Explain the rule", "synthesis", "discussion"),
        ],
        subjects=("science", "ict", "creative_arts", "mathematics",
                  "english", "social_studies"),
        verbs=("identify", "observe", "classify", "categorise", "categorize",
               "sort", "group", "name", "describe", "distinguish"),
        activities=("observation", "classification", "demonstration"),
        assessments=("oral", "sorting task", "labelled diagram"),
        starter="object_observation", plenary="explain_rule",
    ),
    # 2 — DEMONSTRATE → GUIDED PRACTICE → INDEPENDENT APPLICATION
    _p(
        "demonstrate_practice_apply", "Demonstrate → Guided Practice → Apply",
        "The teacher demonstrates the procedure, learners practise with "
        "support, then apply it alone — the default for procedural skills.",
        [
            PatternStep("Demonstration", "input", "demonstration"),
            PatternStep("Guided practice", "guided", "practical", True),
            PatternStep("Independent application", "independent", "practical",
                        True),
        ],
        subjects=("mathematics", "ict", "career_technology", "phe",
                  "creative_arts", "english"),
        verbs=("demonstrate", "perform", "solve", "calculate", "construct",
               "practise", "practice", "use", "apply", "measure", "draw",
               "operate"),
        activities=("demonstration", "practical", "problem_solving", "reading",
                    "writing"),
        assessments=("practical task", "written exercise", "observation"),
        starter="demonstration_teaser", plenary="independent_check",
    ),
    # 3 — PROBLEM SCENARIO → INVESTIGATE → SOLVE
    _p(
        "scenario_investigate_solve", "Scenario → Investigate → Solve",
        "A real problem frames the lesson; learners investigate and report a "
        "solution — for inquiry and problem-solving indicators.",
        [
            PatternStep("Problem scenario", "input", "discussion"),
            PatternStep("Investigation", "guided", "investigation", True),
            PatternStep("Solve and report", "independent", "problem_solving",
                        True),
        ],
        subjects=("mathematics", "science", "social_studies", "ict"),
        verbs=("investigate", "solve", "explore", "analyse", "analyze",
               "determine", "find", "examine", "calculate"),
        activities=("investigation", "problem_solving", "analysis"),
        assessments=("investigation report", "written solution", "oral"),
        starter="quick_scenario", plenary="report_findings",
    ),
    # 4 — COMPARE → JUSTIFY → APPLY
    _p(
        "compare_justify_apply", "Compare → Justify → Apply",
        "Learners contrast two examples, justify the difference and apply the "
        "distinction — for comparison and evaluation indicators.",
        [
            PatternStep("Compare", "input", "comparison"),
            PatternStep("Justify", "guided", "discussion"),
            PatternStep("Apply the distinction", "independent", "comparison",
                        True),
        ],
        subjects=("english", "rme", "social_studies", "science", "ict",
                  "mathematics"),
        verbs=("compare", "contrast", "differentiate", "distinguish",
               "justify", "evaluate", "critique", "assess", "analyse",
               "analyze"),
        activities=("comparison", "discussion", "analysis", "reading"),
        assessments=("comparison chart", "justified answer", "oral"),
        starter="contrast_pairs", plenary="justify_choice",
    ),
    # 5 — RETRIEVE PRIOR LEARNING → MISCONCEPTION CHALLENGE → REBUILD
    _p(
        "retrieve_challenge_rebuild", "Retrieve → Challenge → Rebuild",
        "Reactivate prior learning, confront a known misconception, then "
        "rebuild the correct understanding — for correction and re-teach "
        "situations.",
        [
            PatternStep("Retrieve prior learning", "input", "reflection"),
            PatternStep("Misconception challenge", "guided", "discussion"),
            PatternStep("Rebuild the concept", "independent", "writing", True),
        ],
        subjects=("mathematics", "science", "english", "rme", "ict"),
        verbs=("correct", "revise", "review", "evaluate", "explain",
               "justify", "demonstrate", "redraft"),
        activities=("reflection", "discussion", "writing", "problem_solving"),
        assessments=("redrafted work", "oral justification", "written"),
        starter="misconception_probe", plenary="misconception_correction",
    ),
    # 6 — MODEL → PAIR PRACTICE → INDIVIDUAL PERFORMANCE
    _p(
        "model_pair_individual", "Model → Pair Practice → Perform",
        "The teacher models the target performance, pairs rehearse it, then "
        "each learner performs alone — language and performance skills.",
        [
            PatternStep("Model", "input", "demonstration"),
            PatternStep("Pair practice", "guided", "reading", True),
            PatternStep("Individual performance", "independent", "writing",
                        True),
        ],
        subjects=("english", "rme", "creative_arts", "phe"),
        verbs=("read", "write", "say", "pronounce", "recite", "perform",
               "speak", "listen", "compose", "demonstrate", "model"),
        activities=("reading", "writing", "demonstration", "practical"),
        assessments=("performance", "oral", "written piece"),
        starter="vocabulary_activation", plenary="learner_explanation",
    ),
    # 7 — CASE STUDY → GROUP ANALYSIS → PRESENTATION
    _p(
        "case_study_group_present", "Case Study → Analyse → Present",
        "A case or source is analysed in groups and findings are presented — "
        "for social, civic and textual analysis.",
        [
            PatternStep("Case study", "input", "reading"),
            PatternStep("Group analysis", "guided", "analysis", True),
            PatternStep("Group presentation", "independent", "discussion"),
        ],
        subjects=("social_studies", "rme", "english", "science", "ict"),
        verbs=("analyse", "analyze", "examine", "discuss", "interpret",
               "evaluate", "present", "argue", "justify", "critique"),
        activities=("analysis", "reading", "discussion", "investigation"),
        assessments=("group presentation", "oral", "written analysis"),
        starter="quick_scenario", plenary="group_presentation_recap",
    ),
    # 8 — QUESTION → DISCOVERY → EVIDENCE → CONCLUSION
    _p(
        "question_discovery_conclude", "Question → Discover → Conclude",
        "A question drives discovery; learners collect evidence and draw a "
        "conclusion — scientific inquiry.",
        [
            PatternStep("Question and predict", "input", "investigation"),
            PatternStep("Discovery and evidence", "guided", "observation",
                        True),
            PatternStep("Draw conclusions", "synthesis", "analysis"),
        ],
        subjects=("science", "mathematics", "ict"),
        verbs=("predict", "observe", "investigate", "experiment", "record",
               "measure", "analyse", "analyze", "conclude", "explain",
               "discover"),
        activities=("investigation", "observation", "analysis", "practical"),
        assessments=("investigation report", "recorded evidence", "oral"),
        starter="prediction", plenary="conclusion_check",
    ),
    # 9 — EXAMPLE → NON-EXAMPLE → SORT → JUSTIFY
    _p(
        "example_nonexample_sort", "Example → Non-Example → Sort → Justify",
        "Contrast examples with non-examples, sort, then justify — concept "
        "formation.",
        [
            PatternStep("Examples and non-examples", "input", "classification"),
            PatternStep("Sort", "guided", "classification", True),
            PatternStep("Justify the groups", "independent", "discussion"),
        ],
        subjects=("mathematics", "science", "english", "ict", "rme",
                  "social_studies"),
        verbs=("identify", "classify", "categorise", "categorize", "sort",
               "distinguish", "differentiate", "justify", "define"),
        activities=("classification", "comparison", "discussion"),
        assessments=("sorting task", "justification", "oral"),
        starter="object_observation", plenary="explain_rule",
    ),
    # 10 — PRACTICAL TASK → TROUBLESHOOT → PEER EXPLAIN
    _p(
        "practical_troubleshoot_explain", "Practical → Troubleshoot → Explain",
        "Learners attempt the practical task, diagnose and fix the failure, "
        "then explain it to a peer — technical and digital skills.",
        [
            PatternStep("Practical task", "guided", "practical", True),
            PatternStep("Troubleshoot", "guided", "demonstration"),
            PatternStep("Peer explanation", "independent", "discussion"),
        ],
        subjects=("ict", "career_technology", "creative_arts", "science",
                  "phe"),
        verbs=("operate", "troubleshoot", "assemble", "construct", "repair",
               "perform", "demonstrate", "practise", "practice", "use",
               "maintain"),
        activities=("practical", "demonstration", "discussion"),
        assessments=("practical task", "observation", "peer explanation"),
        starter="diagnostic_question", plenary="teach_a_peer",
    ),
    # 11 — STORY / SCENARIO → DISCUSSION → APPLICATION
    _p(
        "story_discussion_apply", "Story → Discuss → Apply",
        "A story or scenario opens respectful discussion, then learners apply "
        "the value or idea — RME and values-based social studies.",
        [
            PatternStep("Story or scenario", "input", "reading"),
            PatternStep("Discussion", "guided", "discussion"),
            PatternStep("Apply to life", "independent", "writing", True),
        ],
        subjects=("rme", "social_studies", "english", "creative_arts"),
        verbs=("discuss", "reflect", "apply", "explain", "justify",
               "evaluate", "narrate", "describe", "appreciate", "share"),
        activities=("discussion", "reading", "reflection", "writing"),
        assessments=("oral", "written reflection", "role play"),
        starter="quick_scenario", plenary="application_commitment",
    ),
    # 12 — RETRIEVAL → NEW CONCEPT → PRACTICE → CHECK
    _p(
        "retrieval_concept_practice_check", "Retrieve → Teach → Practise → Check",
        "Reactivate, introduce the new concept, practise, then check — the "
        "general direct-teaching sequence for new content.",
        [
            PatternStep("Retrieve", "input", "reflection"),
            PatternStep("New concept", "input", "demonstration"),
            PatternStep("Practice", "guided", "problem_solving", True),
            PatternStep("Check", "independent", "problem_solving", True),
        ],
        subjects=("mathematics", "english", "science", "social_studies",
                  "ict", "rme", "career_technology"),
        verbs=("identify", "state", "define", "describe", "explain",
               "demonstrate", "apply", "practise", "practice", "use",
               "calculate", "read", "write"),
        activities=("demonstration", "problem_solving", "reading", "writing",
                    "practical"),
        assessments=("written exercise", "oral", "practical task"),
        starter="retrieval", plenary="exit_question",
    ),
    # 13 — CREATIVE DEMONSTRATION → GUIDED CREATION → SHARE/CRITIQUE
    _p(
        "creative_demo_creation_critique", "Demonstrate → Create → Critique",
        "Demonstrate the technique, guide creation, then share and critique — "
        "creative and productive subjects.",
        [
            PatternStep("Creative demonstration", "input", "demonstration"),
            PatternStep("Guided creation", "guided", "creation", True),
            PatternStep("Share and critique", "independent", "discussion"),
        ],
        subjects=("creative_arts", "career_technology", "english"),
        verbs=("create", "design", "compose", "produce", "construct", "draw",
               "make", "perform", "critique", "evaluate", "revise", "present"),
        activities=("creation", "practical", "demonstration"),
        assessments=("created work", "rubric", "peer critique"),
        starter="demonstration_teaser", plenary="share_and_critique",
    ),
    # 14 — MOVEMENT DEMONSTRATION → GUIDED PRACTICE → PERFORMANCE
    _p(
        "movement_demo_practice_perform", "Demonstrate Movement → Practise → Perform",
        "Demonstrate the movement or routine, practise with feedback, then "
        "perform — physical education and early-years movement.",
        [
            PatternStep("Movement demonstration", "input", "demonstration"),
            PatternStep("Guided practice", "guided", "practical", True),
            PatternStep("Performance", "independent", "practical", True),
        ],
        subjects=("phe", "creative_arts", "early_childhood", "nursery"),
        verbs=("perform", "demonstrate", "practise", "practice", "move",
               "dance", "run", "jump", "throw", "catch", "balance", "play",
               "coordinate"),
        activities=("practical", "demonstration"),
        assessments=("performance", "observation", "peer feedback"),
        starter="warm_up_game", plenary="cool_down_reflection",
    ),
]

PATTERN_BY_ID: Dict[str, LessonPattern] = {p.id: p for p in PATTERNS}


def catalog_size() -> int:
    return len(PATTERNS)


def pattern_for_id(pattern_id: str) -> Optional[LessonPattern]:
    return PATTERN_BY_ID.get((pattern_id or "").strip())


#: Steps that follow the INDICATOR's own activity type rather than the
#: pattern's default bank — used by the lesson builder to keep a procedural
#: indicator procedural inside any pattern.
def indicator_following_steps(pattern: LessonPattern) -> List[PatternStep]:
    return [s for s in pattern.steps if s.use_indicator_activity]


# ── Pattern selection (Layer 3: scored, deterministic) ──────────────────────


@dataclass
class SelectionContext:
    """Everything the scorer needs about the lesson being planned.

    All fields are optional; missing fields simply do not contribute to the
    score. The context is built by the CALLER (the allocation engine builds
    one per lesson in a batch) from curriculum evidence, the subject pedagogy
    profile and the batch history (Layer 4).
    """

    subject_profile: str = ""
    class_level: str = ""
    indicator_text: str = ""
    indicator_activity: str = ""
    objective_text: str = ""
    duration_minutes: int = 60
    class_size: int = 0
    #: Evidence verbs (curriculum_action_verbs from Layer 1) — the strongest
    #: signal when an official record exists for this indicator.
    evidence_verbs: Tuple[str, ...] = ()
    evidence_activity_patterns: Tuple[str, ...] = ()
    #: Source TLRs from the teacher's scheme (resource availability).
    source_resources: Tuple[str, ...] = ()
    #: Position of this lesson inside the batch/term (0 = first).
    lesson_position: int = 0
    #: Fingerprints of patterns already used in this batch, most-recent-last
    #: (Layer 4 anti-repetition input).
    recent_pattern_ids: Tuple[str, ...] = ()
    #: Reference to the previous indicator text (continuity).
    previous_indicator: str = ""

    def level_band_value(self) -> str:
        return level_band(self.class_level)


def _verb_overlap(a: Sequence[str], b: Sequence[str]) -> float:
    """Token-set overlap between two verb collections in [0, 1]."""
    if not a or not b:
        return 0.0
    sa = {str(x).strip().lower() for x in a if str(x).strip()}
    sb = {str(x).strip().lower() for x in b if str(x).strip()}
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / max(len(sa), 1)


def _resource_weight(pattern: LessonPattern, ctx: SelectionContext) -> float:
    """Penalise resource-hungry patterns when the scheme lists no equipment."""
    if pattern.resource_needs == "LOW":
        return 0.0
    # MEDIUM patterns need real apparatus; without source resources they are
    # a slightly worse fit (bounded so it never overrides curriculum fit).
    blob = " ".join(ctx.source_resources).lower()
    if not ctx.source_resources:
        return 0.4
    markers = ("computer", "device", "laptop", "projector", "internet",
               "instrument", "tool", "material", "specimen", "apparatus",
               "kit", "machine")
    if any(m in blob for m in markers):
        return 0.0
    return 0.3


def _duration_fit(pattern: LessonPattern, ctx: SelectionContext) -> float:
    d = int(ctx.duration_minutes or 0)
    if d <= 0:
        return 0.0
    if d < pattern.min_duration:
        # Needs more time than the period allows — a real, bounded penalty.
        return 0.3 * (pattern.min_duration - d) / max(pattern.min_duration, 1)
    if d > pattern.max_duration:
        return 0.1
    return 0.0


def _class_size_fit(pattern: LessonPattern, ctx: SelectionContext) -> float:
    n = int(ctx.class_size or 0)
    if n <= 0:
        return 0.0
    if n >= 60:
        return 0.0 if pattern.resource_needs == "LOW" else 0.15
    return 0.0


def _level_fit(pattern: LessonPattern, ctx: SelectionContext) -> float:
    if not pattern.suitable_levels:
        return 0.0
    band = ctx.level_band_value()
    if not band:
        return 0.1
    return 0.0 if band in pattern.suitable_levels else 0.5


#: Evidence activity patterns that signal a pattern id. Keyed by phrase found
#: inside a corpus record's exemplar_activity_patterns / assessment patterns.
_EVIDENCE_PATTERN_HINTS: Dict[str, Tuple[str, ...]] = {
    "classify": ("observe_classify_explain", "example_nonexample_sort"),
    "sort": ("example_nonexample_sort", "observe_classify_explain"),
    "group": ("example_nonexample_sort", "observe_classify_explain"),
    "predict": ("question_discovery_conclude", "scenario_investigate_solve"),
    "investigat": ("question_discovery_conclude", "scenario_investigate_solve"),
    "experiment": ("question_discovery_conclude",),
    "demonstrat": ("demonstrate_practice_apply",
                   "creative_demo_creation_critique",
                   "movement_demo_practice_perform"),
    "role play": ("model_pair_individual", "story_discussion_apply"),
    "case study": ("case_study_group_present",),
    "debate": ("compare_justify_apply", "story_discussion_apply"),
    "compare": ("compare_justify_apply",),
    "create": ("creative_demo_creation_critique",),
    "design": ("creative_demo_creation_critique",),
    "present": ("case_study_group_present",),
    "model": ("model_pair_individual",),
    "write": ("model_pair_individual", "story_discussion_apply"),
    "read": ("model_pair_individual", "case_study_group_present"),
    "story": ("story_discussion_apply",),
    "scenario": ("scenario_investigate_solve", "story_discussion_apply"),
    "solve": ("scenario_investigate_solve",),
    "practise": ("demonstrate_practice_apply", "movement_demo_practice_perform"),
    "practice": ("demonstrate_practice_apply", "movement_demo_practice_perform"),
    "perform": ("movement_demo_practice_perform", "model_pair_individual"),
    "troubleshoot": ("practical_troubleshoot_explain",),
    "peer": ("practical_troubleshoot_explain", "case_study_group_present"),
    "assess": ("compare_justify_apply", "retrieve_challenge_rebuild"),
}


def score_pattern(pattern: LessonPattern, ctx: SelectionContext) -> float:
    """Curriculum FIT score for one pattern (higher is better).

    The score is deliberately fit-dominated:

    * indicator activity-type match        — up to +1.0  (the leading term)
    * subject suitability / compatibility  — gate + up to +0.8
    * indicator-verb match                 — up to +0.5
    * evidence (corpus/teacher) alignment  — up to +0.6
    * objective-text verb match            — up to +0.25
    * duration / level / class-size / resource fit — bounded penalties

    Novelty is NOT part of this function: it is applied separately (Layer 4)
    as a small, bounded penalty so variation can only break ties between
    *equally fitted* patterns. Curriculum alignment always outweighs novelty.
    """
    # Hard gate: incompatible subjects never win, whatever else matches.
    if pattern.compatible_subjects and ctx.subject_profile and \
            ctx.subject_profile not in pattern.compatible_subjects:
        return -10.0

    score = 0.0

    # 1. Indicator activity-type match — the primary curriculum signal.
    if ctx.indicator_activity:
        if ctx.indicator_activity in pattern.suitable_activity_types:
            score += 1.0
        elif _verb_overlap([ctx.indicator_activity],
                           pattern.suitable_activity_types) > 0:
            score += 0.3

    # 2. Subject suitability.
    if not pattern.compatible_subjects or (
            ctx.subject_profile and
            ctx.subject_profile in pattern.compatible_subjects):
        score += 0.8

    # 3. Evidence (corpus / teacher) alignment — the official record's verbs.
    if ctx.evidence_verbs:
        score += 0.6 * _verb_overlap(ctx.evidence_verbs, pattern.suitable_verbs)

    # 4. Indicator-verb match.
    if ctx.indicator_text:
        words = set(re.findall(r"[a-z]+", ctx.indicator_text.lower()))
        score += 0.5 * _verb_overlap(words, pattern.suitable_verbs)

    # 5. Objective-text alignment.
    if ctx.objective_text:
        words = set(re.findall(r"[a-z]+", ctx.objective_text.lower()))
        score += 0.25 * _verb_overlap(words, pattern.suitable_verbs)

    # 6. Evidence activity-pattern alignment (corpus hints).
    if ctx.evidence_activity_patterns:
        blob = " ".join(ctx.evidence_activity_patterns).lower()
        hits = set()
        for marker, ids in _EVIDENCE_PATTERN_HINTS.items():
            if marker in blob:
                hits.update(ids)
        if pattern.id in hits:
            score += 0.35

    # 7. Bounded practicality penalties.
    score -= _resource_weight(pattern, ctx)
    score -= _duration_fit(pattern, ctx)
    score -= _class_size_fit(pattern, ctx)
    score -= _level_fit(pattern, ctx)

    return score


#: Patterns whose MAIN structure is the subject's canonical way of teaching a
#: given activity type. Used to keep position-0 lessons on the proven path and
#: to raise the floor of an otherwise-unbiased selection.
_CANONICAL_BY_ACTIVITY: Dict[str, Tuple[str, ...]] = {
    "problem_solving": ("demonstrate_practice_apply",
                        "retrieval_concept_practice_check"),
    "investigation": ("question_discovery_conclude",
                      "scenario_investigate_solve"),
    "practical": ("demonstrate_practice_apply",
                  "movement_demo_practice_perform"),
    "classification": ("observe_classify_explain", "example_nonexample_sort"),
    "observation": ("question_discovery_conclude", "observe_classify_explain"),
    "reading": ("model_pair_individual", "case_study_group_present"),
    "writing": ("model_pair_individual", "story_discussion_apply"),
    "discussion": ("story_discussion_apply", "case_study_group_present"),
    "comparison": ("compare_justify_apply", "example_nonexample_sort"),
    "creation": ("creative_demo_creation_critique",),
    "analysis": ("case_study_group_present", "scenario_investigate_solve"),
    "reflection": ("retrieve_challenge_rebuild", "story_discussion_apply"),
    "demonstration": ("demonstrate_practice_apply",
                      "creative_demo_creation_critique",
                      "movement_demo_practice_perform"),
}

#: Subject canonical first patterns — the subject's own pedagogical home.
_CANONICAL_BY_SUBJECT: Dict[str, Tuple[str, ...]] = {
    "mathematics": ("demonstrate_practice_apply", "scenario_investigate_solve"),
    "science": ("question_discovery_conclude", "observe_classify_explain"),
    "english": ("model_pair_individual", "story_discussion_apply"),
    "social_studies": ("case_study_group_present", "story_discussion_apply"),
    "ict": ("demonstrate_practice_apply", "practical_troubleshoot_explain"),
    "rme": ("story_discussion_apply", "compare_justify_apply"),
    "phe": ("movement_demo_practice_perform",),
    "creative_arts": ("creative_demo_creation_critique",),
    "career_technology": ("demonstrate_practice_apply",
                          "practical_troubleshoot_explain"),
    "early_childhood": ("movement_demo_practice_perform",),
    "nursery": ("movement_demo_practice_perform",),
    "generic": ("retrieval_concept_practice_check",),
}


def canonical_pattern_ids(ctx: SelectionContext) -> Tuple[str, ...]:
    """The patterns that are this lesson's pedagogical home (fit floor)."""
    ids: List[str] = []
    if ctx.indicator_activity in _CANONICAL_BY_ACTIVITY:
        ids.extend(_CANONICAL_BY_ACTIVITY[ctx.indicator_activity])
    if ctx.subject_profile in _CANONICAL_BY_SUBJECT:
        for pid in _CANONICAL_BY_SUBJECT[ctx.subject_profile]:
            if pid not in ids:
                ids.append(pid)
    if not ids:
        ids.append("retrieval_concept_practice_check")
    return tuple(ids)


def _best_fit_canon(canon: Set[str], scores: Dict[str, float]) -> Optional[str]:
    ranked = sorted(
        (pid for pid in canon if pid in scores),
        key=lambda pid: (-scores[pid], pid),
    )
    return ranked[0] if ranked else None


def select_pattern(
    ctx: SelectionContext,
    *,
    candidates: Optional[Sequence[LessonPattern]] = None,
    novelty_penalty: Optional[Dict[str, float]] = None,
) -> Tuple[LessonPattern, float, Dict[str, float]]:
    """Select the best-fitting pattern for a lesson, deterministically.

    Returns ``(pattern, fit_score, novelty_adjusted_scores)``.

    ``novelty_penalty`` (Layer 4) maps pattern ids to a SMALL penalty — it is
    deliberately bounded (callers pass ≤ ~0.6) so it can only reorder patterns
    that are otherwise close in curriculum fit. Curriculum alignment always
    outweighs novelty: a pattern that genuinely fits the indicator wins even
    when it was used in the previous lesson.

    Ties are broken by catalog order, so the result is a pure function of the
    inputs (no randomness anywhere in the path).
    """
    pool = list(candidates) if candidates is not None else list(PATTERNS)
    if not pool:
        raise ValueError("pattern catalog is empty")

    canon = set(canonical_pattern_ids(ctx))
    scores: Dict[str, float] = {p.id: score_pattern(p, ctx) for p in pool}

    adjusted = dict(scores)
    for pid, penalty in (novelty_penalty or {}).items():
        if pid in adjusted:
            adjusted[pid] = float(adjusted[pid]) - float(penalty)

    # Guardian: novelty must not push a canonical pattern below every
    # non-canonical alternative. An alien pattern only wins on genuine fit.
    best_canon = _best_fit_canon(canon, scores)
    if best_canon is not None:
        floor = scores[best_canon] - 0.25
        for pid in list(adjusted):
            if pid not in canon and adjusted[pid] > floor:
                adjusted[pid] = min(adjusted[pid], floor)

    # Tie-break: prefer the canonical (subject/activity home) pattern, in the
    # canonical preference order, then catalog order. This keeps a subject on
    # its proven path when fit is genuinely equal — the fit floor above has
    # already guaranteed an alien pattern cannot win on novelty alone.
    canon_order = {pid: i for i, pid in enumerate(canonical_pattern_ids(ctx))}
    best = max(pool, key=lambda p: (
        adjusted[p.id],
        -(canon_order.get(p.id, 10_000)),
        -PATTERNS.index(p) if p in PATTERNS else 0,
    ))
    return best, scores[best.id], adjusted


def novelty_penalty(
    ctx: SelectionContext,
    *,
    recency_weight: float = 0.35,
    max_penalty: float = 0.6,
) -> Dict[str, float]:
    """Bounded anti-repetition penalty from recent pattern usage (Layer 4).

    The lesson that used pattern X most recently contributes the largest
    penalty; older uses decay. Total penalty per pattern is capped by
    ``max_penalty`` so curriculum fit (the leading score term can be ~2.5) is
    always able to overcome it. Missing history ⇒ no penalty at all.
    """
    recent = list(ctx.recent_pattern_ids or ())
    if not recent:
        return {}
    # Most recent lesson first, so recency maps onto penalty magnitude.
    ordered = list(reversed(recent))
    penalty: Dict[str, float] = {}
    for offset, pid in enumerate(ordered):
        magnitude = recency_weight * (1.0 / (1.0 + 0.5 * offset))
        current = penalty.get(pid, 0.0)
        penalty[pid] = min(max_penalty, current + magnitude)
    return penalty


__all__ = [
    "NURSERY_BAND", "KG_BAND", "LOWER_BAND", "UPPER_BAND", "JHS_BAND",
    "SHS_BAND", "level_band", "PatternStep", "LessonPattern", "PATTERNS",
    "PATTERN_BY_ID", "catalog_size", "pattern_for_id",
    "indicator_following_steps", "SelectionContext", "score_pattern",
    "select_pattern", "novelty_penalty", "canonical_pattern_ids",
]

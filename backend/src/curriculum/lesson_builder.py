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
  * INDICATOR-SPECIFIC CONTENT: the starter, main activities, assessment,
    plenary, resources, vocabulary, core competencies and references are
    derived from the indicator's *activity type* (what learners must DO) and
    *Bloom level* (how deeply), not from one fixed sentence skeleton. Two
    lessons for different indicators therefore teach and assess different
    things — the variation comes from the curriculum, never from randomness.
  * The three phases tell ONE instructional story:
        starter activates prerequisite knowledge
        → teacher introduces/elicits the new concept
        → learners practise the target skill
        → assessment measures that same skill
        → plenary consolidates and links forward.
  * Objectives are learner-centred, observable and measurable.
  * Resources are realistic for Ghanaian classrooms and support THIS lesson's
    actual activities.
  * Teacher-supplied keywords / TLRs / competencies / references are always
    preserved and never replaced.
  * Variation is deterministic: subject + indicator activity type + lesson
    position + previous/next context. The same input always yields the same
    baseline lesson.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from ..models import (
    AllocatedIndicator, TermConfig, LessonPlan, LessonStatus, Subject,
    ClassLevel, LearningObjective, TeachingActivity,
)
from .pedagogy import profile_for_subject, SubjectPedagogy

_CODE_RE = re.compile(r"^\s*[BbKk]?\d+(?:\.\d+){2,4}[.:]?\s*")

#: Legacy learner-facing prefixes stripped before re-phrasing.
_LEARNER_PREFIXES = (
    "learners can ", "students can ", "pupils can ",
    "learners should be able to ", "students should be able to ",
    "by the end of the lesson, learners should be able to: ",
    "by the end of the lesson, learners should be able to ",
    "by the end of the lesson, the learner should be able to: ",
    "by the end of the lesson, the learner should be able to ",
)

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "their", "this", "that", "these", "those", "they", "them", "it", "its",
    "by", "as", "at", "from", "into", "using", "use", "able", "can", "will",
    "should", "which", "who", "how", "what", "when", "where", "why", "be",
    "is", "are", "was", "were", "has", "have", "had", "understand",
    "knowledge", "skill", "skills", "lesson", "learners", "learner",
    "students", "pupils", "including", "such", "e.g", "eg", "i.e", "ie",
    "correctly", "accurately", "own", "words", "different", "various",
}

# ── Indicator-activity phase banks ─────────────────────────────────────────
# Each entry is (phase_name, template). Templates may use {focus},
# {focus_short}, {verb}, {resource}, {strand}, {sub_strand}, {skill},
# {topic}, {bloom}, {evidence}, {class_level}.
# The bank is keyed by the indicator's activity type so a problem-solving
# lesson and an investigation lesson do not share one skeleton.

_PHASE_BANK: Dict[str, List[Tuple[str, str]]] = {
    "problem_solving": [
        ("Teacher demonstration (worked example)",
         "Work through one fully-reasoned example of {focus_short} on the board, "
         "thinking aloud at every step so learners see the method, not only the "
         "answer."),
        ("Guided practice",
         "In mixed-ability pairs, learners solve a parallel problem on "
         "{focus_short}. Move between pairs and correct any wrong step "
         "immediately."),
        ("Independent practice",
         "Each learner solves two problems on {focus_short} alone, then the "
         "class analyses one common wrong answer and explains why it fails."),
    ],
    "investigation": [
        ("Prediction",
         "Pose a prediction question about {focus_short} ('What do you expect to "
         "happen, and why?'). Record two or three predictions on the board "
         "without judging them yet."),
        ("Investigation",
         "In groups, learners carry out the activity for {focus_short} using "
         "{resource}. They record what they observe or measure in a simple "
         "table."),
        ("Explanation",
         "Groups explain how their evidence supports or contradicts the earlier "
         "prediction about {focus_short}. Correct misconceptions and link the "
         "findings to {strand}."),
    ],
    "practical": [
        ("Demonstration",
         "Demonstrate the technique or process for {focus_short}, emphasising "
         "safety and the correct order of steps."),
        ("Guided practical",
         "Learners carry out the practical task for {focus_short} in small "
         "groups using {resource}, with the teacher correcting technique."),
        ("Application",
         "Learners apply what they practised to complete one task on "
         "{focus_short} and inspect their own product."),
    ],
    "classification": [
        ("Presentation of examples",
         "Present two contrasting examples linked to {focus_short} and ask "
         "learners what is the same and what is different."),
        ("Classification activity",
         "Learners sort/group the given items according to the rule for "
         "{focus_short}, explaining the basis of each group using {resource}."),
        ("Accuracy check",
         "Review the groups as a class, challenge one borderline item and agree "
         "the correct classification for {focus_short}."),
    ],
    "observation": [
        ("Directed observation",
         "Guide learners to observe {focus_short} closely, showing them exactly "
         "what features to look for using {resource}."),
        ("Recording",
         "Learners record their observations of {focus_short} in a simple table "
         "or labelled diagram, using the correct terms."),
        ("Discussion of findings",
         "Compare observations across groups and draw out the key pattern about "
         "{focus_short}."),
    ],
    "reading": [
        ("Vocabulary and preview",
         "Introduce the key words needed for {focus_short} and let learners "
         "preview the text, predicting its content from the title."),
        ("Guided reading",
         "Read the text for {focus_short} together, pausing to question and "
         "clarify; learners underline evidence relevant to the indicator."),
        ("Comprehension task",
         "Learners answer comprehension questions on {focus_short}, giving "
         "evidence from the text rather than guessing."),
    ],
    "writing": [
        ("Model text",
         "Present a short model showing how {focus_short} is done. Highlight "
         "the features learners must reproduce."),
        ("Guided writing",
         "Learners plan and draft their own piece for {focus_short} with the "
         "teacher's support, using the model as a scaffold."),
        ("Independent writing",
         "Each learner completes and improves their piece on {focus_short} "
         "against a short checklist."),
    ],
    "discussion": [
        ("Stimulus",
         "Present a scenario, question or source about {focus_short} and let "
         "learners identify the key issue involved."),
        ("Structured discussion",
         "Organise a group discussion on {focus_short}. Learners must give "
         "reasons and respond to other views."),
        ("Application",
         "Learners apply the discussion to a local situation, answering 'what "
         "would we do here?' about {focus_short}."),
    ],
    "comparison": [
        ("First item",
         "Present the first item for {focus_short} and have learners note its "
         "features."),
        ("Second item",
         "Present the second item and have learners note how it differs for "
         "{focus_short}."),
        ("Comparison task",
         "Learners complete a comparison chart for {focus_short}, stating the "
         "similarities and differences clearly."),
    ],
    "creation": [
        ("Inspiration",
         "Show or perform a short sample connected to {focus_short} so learners "
         "can see what a strong result looks like."),
        ("Creation",
         "Learners create their own work applying {focus_short}, using "
         "{resource}; the teacher supports individuals."),
        ("Critique and revision",
         "Learners display or perform their work and give kind, specific "
         "feedback on {focus_short} before revising."),
    ],
    "analysis": [
        ("Present data/source",
         "Present the data or source linked to {focus_short} and check learners "
         "understand what it shows."),
        ("Analysis",
         "Learners break down the information for {focus_short}, identifying "
         "patterns, causes or relationships."),
        ("Findings",
         "Groups report their findings about {focus_short} and the class agrees "
         "the key conclusion."),
    ],
    "reflection": [
        ("Experience review",
         "Recall the experience or learning so far linked to {focus_short} and "
         "ask learners what stood out."),
        ("Reflection task",
         "Learners reflect on {focus_short} in writing, justifying what they "
         "would keep or change."),
        ("Sharing",
         "Share reflections about {focus_short} and draw out the main lesson."),
    ],
    "demonstration": [
        ("Teacher demonstration",
         "Demonstrate {focus_short} slowly, thinking aloud, and check that every "
         "learner can see and hear."),
        ("Guided imitation",
         "Learners repeat or reproduce the demonstration for {focus_short} with "
         "the teacher's prompts, using {resource}."),
        ("Independent application",
         "Learners perform the task for {focus_short} on their own and check "
         "their work against the demonstrated steps."),
    ],
}

#: Starter templates keyed by activity type — what readiness for THIS activity
#: looks like (a prediction for an investigation, a mental drill for
#: problem-solving, prior vocabulary for reading, …).
_STARTER_BANK: Dict[str, str] = {
    "problem_solving": (
        "Activate the prerequisite skill for {focus_short} with a quick "
        "mental/oral drill: pose two related questions and have the class call "
        "out the method step by step."
    ),
    "investigation": (
        "Pose a short 'what do you think will happen?' question about "
        "{focus_short}. Collect two or three predictions on the board without "
        "judging them yet — this frames the investigation."
    ),
    "practical": (
        "Recall the last practical skill and connect it to {focus_short}. Check "
        "that the workspace and materials needed for today's task are safe and "
        "ready."
    ),
    "classification": (
        "Show two familiar items related to {focus_short} and ask learners how "
        "they would decide which group each belongs to."
    ),
    "observation": (
        "Remind learners what careful observation means for {focus_short} and "
        "ask what features they expect to notice."
    ),
    "reading": (
        "Warm up with quick oral vocabulary practice linked to {focus_short}; "
        "elicit what learners already know about the topic before reading."
    ),
    "writing": (
        "Warm up with quick oral language practice linked to {focus_short}; "
        "elicit the words and structures learners already know."
    ),
    "discussion": (
        "Open with a familiar local scenario or question about {focus_short} "
        "and ask learners to share what they already know."
    ),
    "comparison": (
        "Show one of the items linked to {focus_short} and ask learners what "
        "they already notice about it before comparing with another."
    ),
    "creation": (
        "Show a short sample related to {focus_short} and ask learners what "
        "they notice about how it was made or performed."
    ),
    "analysis": (
        "Present a quick example related to {focus_short} and ask learners what "
        "they think it shows before analysing it in detail."
    ),
    "reflection": (
        "Invite learners to recall what they already experienced or learned "
        "about {focus_short} and share one thing they remember."
    ),
    "demonstration": (
        "Review the prerequisite knowledge for {focus_short} with a short "
        "question-and-answer session and link to the previous lesson."
    ),
}

#: Assessment templates keyed by activity type. Each measures THIS indicator
#: via its own evidence of achievement, not a generic topic.
_ASSESSMENT_BANK: Dict[str, str] = {
    "problem_solving": (
        "Written class exercise of 2-3 problems that test {focus_short}; mark "
        "for correct method and correct answer. Success = {evidence}"
    ),
    "investigation": (
        "Observe learners carrying out {focus_short} against a short checklist, "
        "then ask them to explain their result in writing. Success = {evidence}"
    ),
    "practical": (
        "Assess the finished product or process for {focus_short} against a "
        "short rubric (correct steps, safety, quality). Success = {evidence}"
    ),
    "classification": (
        "A classification exercise on {focus_short}: learners must sort items "
        "and justify each group. Success = {evidence}"
    ),
    "observation": (
        "Check each learner's observation record for {focus_short} and question "
        "them orally on what they noticed. Success = {evidence}"
    ),
    "reading": (
        "Comprehension questions on {focus_short} requiring text evidence, plus "
        "oral reading for learners who struggle with writing. Success = {evidence}"
    ),
    "writing": (
        "Assess the independent writing task for {focus_short} against a short "
        "checklist of features. Success = {evidence}"
    ),
    "discussion": (
        "Ask oral questions and set a short written task requiring a reasoned "
        "view on {focus_short}. Success = {evidence}"
    ),
    "comparison": (
        "Mark the comparison chart for {focus_short} for accurate similarities "
        "and differences. Success = {evidence}"
    ),
    "creation": (
        "Assess the created work or performance on {focus_short} against a "
        "simple rubric (technique, effort, expression). Success = {evidence}"
    ),
    "analysis": (
        "Set a short structured analysis task on {focus_short} and look for "
        "correct reasoning, not recitation. Success = {evidence}"
    ),
    "reflection": (
        "Review each learner's written reflection on {focus_short} and check "
        "they justify their choices. Success = {evidence}"
    ),
    "demonstration": (
        "Ask oral questions and set a short task that tests {focus_short}. "
        "Success = {evidence}"
    ),
}

#: Plenary templates keyed by activity type — consolidates THIS indicator.
_PLENARY_BANK: Dict[str, str] = {
    "problem_solving": (
        "Ask learners to state the method for {focus_short} in one sentence, "
        "summarise the key steps on the board and set one similar problem as "
        "homework."
    ),
    "investigation": (
        "Return to the predictions made at the start: which were supported by "
        "the evidence about {focus_short}? Agree the key finding and what could "
        "be investigated next."
    ),
    "practical": (
        "Review the process for {focus_short}, emphasise safe practice and "
        "discuss how the skill is used in real work."
    ),
    "classification": (
        "Summarise the classifying rule for {focus_short} and ask learners to "
        "give one new example that fits it."
    ),
    "observation": (
        "Summarise the key pattern learners observed about {focus_short} and "
        "ask what they would look for next time."
    ),
    "reading": (
        "Ask learners to summarise {focus_short} in their own words, emphasise "
        "the target language and set a short follow-up reading task."
    ),
    "writing": (
        "Ask two or three learners to share their writing on {focus_short}, "
        "correct common errors and set a short follow-up piece."
    ),
    "discussion": (
        "Summarise the main ideas about {focus_short} and connect them to "
        "learners' own community; ask what responsibility each person has."
    ),
    "comparison": (
        "Summarise how the two items compared for {focus_short} and ask which "
        "difference matters most."
    ),
    "creation": (
        "Celebrate a few examples, summarise the key technique in {focus_short} "
        "and ask what learners would improve next time."
    ),
    "analysis": (
        "Summarise the main conclusion from the analysis of {focus_short} and "
        "ask what evidence supported it."
    ),
    "reflection": (
        "Summarise the lesson about {focus_short} and invite learners to name "
        "one way they will apply it."
    ),
    "demonstration": (
        "Summarise the key points of {focus_short}, ask learners what they "
        "learned and set a short follow-up task."
    ),
}

#: Core competencies genuinely implied by this kind of activity. They may
#: legitimately overlap across lessons, but a practical lesson never blindly
#: inherits the same static set as a reading lesson.
_COMPETENCIES_BY_ACTIVITY: Dict[str, List[str]] = {
    "problem_solving": ["Critical Thinking and Problem Solving", "Communication and Collaboration"],
    "investigation": ["Critical Thinking and Problem Solving", "Communication and Collaboration"],
    "practical": ["Creativity and Innovation", "Communication and Collaboration"],
    "classification": ["Critical Thinking and Problem Solving"],
    "observation": ["Critical Thinking and Problem Solving"],
    "reading": ["Communication and Collaboration", "Digital Literacy"],
    "writing": ["Communication and Collaboration", "Creativity and Innovation"],
    "discussion": ["Communication and Collaboration", "Cultural Identity and Global Citizenship"],
    "comparison": ["Critical Thinking and Problem Solving", "Communication and Collaboration"],
    "creation": ["Creativity and Innovation", "Communication and Collaboration"],
    "analysis": ["Critical Thinking and Problem Solving"],
    "reflection": ["Critical Thinking and Problem Solving", "Personal Development and Leadership"],
    "demonstration": ["Communication and Collaboration"],
}

#: Extra resources a given activity type genuinely needs on top of the subject
#: base resources — so a measurement lesson does not inherit classification
#: materials and vice versa.
_ACTIVITY_RESOURCES: Dict[str, List[str]] = {
    "problem_solving": ["exercise books", "rulers"],
    "investigation": ["simple measuring tools", "recording sheet/table", "specimen or sample"],
    "practical": ["simple tools", "work surface", "safety equipment as needed"],
    "classification": ["sorting cards/items", "labelled containers"],
    "observation": ["hand lens where available", "recording sheet/table"],
    "reading": ["reading text", "word cards"],
    "writing": ["writing materials", "writing frame"],
    "discussion": ["question cards", "chart"],
    "comparison": ["comparison chart/Venn diagram", "the two items to compare"],
    "creation": ["locally available materials for making", "display space"],
    "analysis": ["data/source sheet", "chart"],
    "reflection": ["reflection journal/strips"],
    "demonstration": ["chart", "chalkboard"],
}

#: Essential questions keyed by activity type (indicator-specific).
_ESSENTIAL_BANK: Dict[str, str] = {
    "problem_solving": "How do we work out {focus_short} correctly and show our reasoning?",
    "investigation": "What is the evidence that our explanation of {focus_short} is correct?",
    "practical": "How is {focus_short} done correctly and safely?",
    "classification": "What rule decides how we group the items for {focus_short}?",
    "observation": "What do we notice about {focus_short}, and how can we record it clearly?",
    "reading": "What does the text tell us about {focus_short}?",
    "writing": "How do we organise our writing about {focus_short} clearly?",
    "discussion": "How does {focus_short} affect people and communities in Ghana?",
    "comparison": "How are the two items for {focus_short} alike and different?",
    "creation": "How do we create or perform {focus_short} skilfully?",
    "analysis": "What does the information about {focus_short} actually show?",
    "reflection": "What have we learned about {focus_short} and why does it matter?",
    "demonstration": "What will we learn about {focus_short} and how will we know we have learned it?",
}


def strip_indicator_code(text: str) -> str:
    """Remove a leading curriculum code (e.g. B7.4.3.1.2) from indicator text."""
    if not text:
        return ""
    return _CODE_RE.sub("", text).strip() or text.strip()


_ANY_CODE_RE = re.compile(r"[BbKk]?\d+(?:\.\d+)+")


def is_code_only_indicator(text: str) -> bool:
    """Public alias of :func:`_is_code_only` for cross-module use (the
    allocation engine passes curriculum-context text to the builder and needs
    the same code-only test for KG-style rows)."""
    return _is_code_only(text)


def _is_code_only(text: str) -> bool:
    """True when the indicator text is only a curriculum code / code range.

    KG schemes legitimately print ranges like "K2.1.1.1.1-3" (the parser may
    rejoin them as "K2.1.1.1.1 K2.1.1.1.1-3") with no prose. Such text must
    never be phrased as learner-facing prose ("Learners can K2.1.1.1.1"); the
    source row's sub-strand is the honest lesson focus.
    """
    if not text:
        return True
    without_codes = _ANY_CODE_RE.sub("", text)
    # What remains must be punctuation/whitespace only — any letter means the
    # cell carried real prose alongside the code.
    return not re.search(r"[A-Za-z]", without_codes)


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
    return template.format_map(defaultdict(str, values)).strip()


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


def _first_clause(text: str, max_words: int = 12) -> str:
    """Short, human-readable focus phrase from the indicator text."""
    clean = strip_indicator_code(text or "").strip()
    if not clean:
        return ""
    # Real schemes often carry fragmented codes ("B9.2.1.1 .2 Reflect …",
    # "5.1.1.1 B9. Investigate …"). Strip any orphan code fragment the code
    # regex leaves behind so the lesson never says "about B9" or "about .2".
    clean = re.sub(r"^(?:[Bb]?\d+(?:\.\d+)*\.?\s*)+", "", clean).strip() or clean
    # Stop at the first sentence break or semicolon.
    part = re.split(r"[.;]", clean)[0].strip() or clean
    # Drop a leading lone fragment like ".2", "1)", ":" left by the split.
    part = re.sub(r"^[.:;,)\]]*\s*\d*[.:;,)\]]*\s*", "", part).strip() or part
    words = part.split()
    if len(words) > max_words:
        part = " ".join(words[:max_words])
    return part


def _content_terms(text: str, limit: int = 6) -> List[str]:
    """Extract significant content words from indicator text (for vocabulary)."""
    clean = strip_indicator_code(text or "")
    words = re.findall(r"[A-Za-z][A-Za-z\-']{2,}", clean)
    out: List[str] = []
    for w in words:
        lw = w.lower()
        if lw in _STOPWORDS:
            continue
        if lw.isdigit():
            continue
        if lw not in out:
            out.append(lw)
        if len(out) >= limit:
            break
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


def _activity_key(interp, indicator_text: str) -> Optional[str]:
    """Resolve the phase-bank key for an indicator, or None when the indicator
    does not genuinely express a recognised activity.

    The interpreter defaults to "discussion" when no activity keyword matches,
    so a plain "describe …" indicator would otherwise be forced through the
    discussion skeleton. Returning None in that case lets the SUBJECT pedagogy
    supply the correct structure instead.
    """
    if interp is None:
        return None
    key = (getattr(interp, "activity_type", "") or "").strip().lower()
    if key not in _PHASE_BANK:
        return None
    try:
        from .indicator_interpreter import ACTIVITY_KEYWORDS
        kws = ACTIVITY_KEYWORDS.get(key, [])
    except Exception:
        kws = []
    text_lower = (indicator_text or "").lower()
    if kws and any(k in text_lower for k in kws):
        return key
    return None


def _compose_main_phases(
    profile: SubjectPedagogy,
    fmt: Dict[str, str],
    act_key: Optional[str],
) -> List[Tuple[str, str, float]]:
    """Return (phase_name, description, weight) for the MAIN block.

    Structure follows the indicator's actual activity type when it is
    genuinely expressed; otherwise the subject profile's own pedagogy supplies
    the phases (mathematics: worked example → practice; science: inquiry;
    English: model → production).
    """
    phases: List[Tuple[str, str, float]] = []
    bank = _PHASE_BANK.get(act_key) if act_key else None
    if bank:
        base = [0.30, 0.40, 0.30]
        if len(bank) == 4:
            base = [0.25, 0.30, 0.30, 0.15]
        for i, (name, tmpl) in enumerate(bank):
            weight = base[i] if i < len(base) else 0.25
            phases.append((name, _safe_format(tmpl, **fmt), weight))
        return phases

    # Fallback: subject pedagogy's own phases (still indicator-specific
    # because every profile template embeds the indicator's focus).
    for mp in profile.main_phases:
        phases.append((mp.name, _safe_format(mp.template, **fmt), mp.weight))
    return phases


def build_lesson(
    alloc: AllocatedIndicator,
    config: TermConfig,
    scheme_id: str,
    previous_indicator: Optional[str] = None,
    next_indicator: Optional[str] = None,
) -> LessonPlan:
    """Compose one deterministic, subject-aware, indicator-specific lesson plan."""
    subject_name = (
        config.subject.value if isinstance(config.subject, Subject) else str(config.subject)
    )
    profile: SubjectPedagogy = profile_for_subject(subject_name)
    class_level = (
        config.class_level.value
        if isinstance(config.class_level, ClassLevel) else str(config.class_level)
    )
    # KG classes are developmentally early-childhood regardless of the subject
    # label the file was confirmed under: a KG2 "Numeracy" row is taught
    # through play, songs and concrete objects — not the board-worked examples
    # and written class exercises of the Basic-7-9 mathematics profile. The
    # KG1/KG2 source evidence (play-based authentic assessment, observation
    # checklists, songs and role-play in the resource columns) supports the
    # early-childhood profile for every KG subject area. Basic 1+ keeps the
    # subject profile.
    if class_level in ("KG 1", "KG 2"):
        from .pedagogy import SUBJECT_PROFILES
        profile = SUBJECT_PROFILES["early_childhood"]

    skill = strip_indicator_code(alloc.indicator_description)
    # KG-style rows whose indicator cell holds ONLY a code / code range (e.g.
    # "K2.1.1.1.1-3") carry no teachable prose. Like Nursery rows, the source
    # row itself (sub-strand) is the honest curriculum focus — the bare code
    # is never phrased as learner-facing text or shown in its place.
    if alloc.indicator_description and _is_code_only(alloc.indicator_description):
        skill = ""
    focus_short = "" if skill == "" else (_first_clause(alloc.indicator_description) or skill)
    # Embed the FULL cleaned indicator text into every phase template via
    # {focus} so the lesson visibly teaches this exact indicator (helps the
    # quality gate's exactness check and the teacher's own review).
    if not focus_short or len(focus_short.split()) < 4:
        focus_short = skill or focus_short
    # Nursery-style rows (and KG code-only rows) carry no indicator prose: the
    # source row itself (strand + sub-strand) is the authoritative curriculum
    # focus. The sub-strand names what the lesson actually teaches; the strand
    # alone is never inflated into a fake indicator.
    if not skill and alloc.sub_strand:
        skill = alloc.sub_strand
        focus_short = alloc.sub_strand
    topic = _derive_topic(alloc)
    duration = int(config.lesson_duration_minutes or 60)

    prev_short = _first_clause(previous_indicator or "") if previous_indicator else ""
    next_short = _first_clause(next_indicator or "") if next_indicator else ""

    # Interpret the indicator: what learners must DO and how deeply.
    interp = _interpret(alloc, subject_name)
    act_key = _activity_key(interp, alloc.indicator_description)
    bloom = (getattr(interp, "bloom_level", "") or "understand") if interp else "understand"
    verb = (getattr(interp, "primary_action", "") or "learn") if interp else "learn"
    evidence = (
        getattr(interp, "evidence_of_achievement", "")
        if interp else "Learner demonstrates understanding."
    )
    assessment_mode = (
        getattr(interp, "assessment_mode", "") if interp else ""
    )
    misconceptions = (
        getattr(interp, "misconception_risks", "") if interp else ""
    )

    # The raw code/range is curriculum metadata, not prose: phase templates
    # that reference {indicators} get the honest focus text instead when the
    # source cell was code-only.
    indicators_for_templates = (
        "" if alloc.indicator_description and _is_code_only(alloc.indicator_description)
        else (alloc.indicator_description or "")
    )
    fmt = dict(
        skill=skill, focus=skill, focus_short=focus_short, topic=topic,
        indicators=indicators_for_templates,
        strand=alloc.strand or "", sub_strand=alloc.sub_strand or "",
        class_level=class_level, prev=prev_short, next=next_short,
        content_standard=alloc.content_standard_description or "",
        verb=verb, bloom=bloom, evidence=evidence, activity=act_key,
        resource="",  # filled per-phase below
    )

    # ── STARTER — prepares learners for THIS indicator's activity ───────
    starter_line = _STARTER_BANK.get(act_key) or profile.starter_template
    starter = _safe_format(starter_line, **fmt)
    if prev_short:
        starter = f"Build on the previous lesson ('{prev_short}'). " + starter
    if misconceptions and "Monitor for general" not in misconceptions:
        starter += f" Watch for: {misconceptions}"
    intro = starter

    # ── MAIN — phases follow the indicator's activity type ──────────────
    starter_min = max(5, round(duration * 0.15))
    plenary_min = max(5, round(duration * 0.20))
    phase_specs = _compose_main_phases(profile, fmt, act_key)
    main_total = max(duration - starter_min - plenary_min, len(phase_specs))
    phase_minutes = _distribute(main_total, [p[2] for p in phase_specs])

    main_activities: List[TeachingActivity] = []
    learner_activities: List[TeachingActivity] = []
    teacher_activities: List[TeachingActivity] = []
    for (phase_name, desc, _), minutes in zip(phase_specs, phase_minutes):
        main_activities.append(TeachingActivity(
            phase=phase_name.upper(), description=desc,
            duration_minutes=minutes, resources=[],
        ))
        learner_activities.append(TeachingActivity(
            phase="LEARNER",
            description=_learner_task(phase_name, focus_short),
            duration_minutes=minutes, resources=[],
        ))
        teacher_activities.append(TeachingActivity(
            phase="TEACHER",
            description=_teacher_move(phase_name, focus_short),
            duration_minutes=minutes, resources=[],
        ))

    # ── ASSESSMENT — measures THIS indicator's evidence ─────────────────
    assessment_tmpl = _ASSESSMENT_BANK.get(act_key) or profile.assessment_template
    assessment = _safe_format(assessment_tmpl, **fmt)
    if assessment_mode and assessment_mode.lower() not in assessment.lower():
        assessment += f" Assessment mode: {assessment_mode}"

    # ── PLENARY — consolidates THIS indicator ───────────────────────────
    conclusion = _safe_format(
        _PLENARY_BANK.get(act_key) or profile.plenary_template, **fmt
    )
    if next_short:
        conclusion += f" Preview the next lesson ('{next_short}')."

    # ── Differentiation — tied to the actual task ───────────────────────
    differentiation = "\n".join([
        f"Support: {_safe_format(profile.support_template, **fmt)}",
        f"Extension: {_safe_format(profile.extension_template, **fmt)}",
        f"Grouping: {profile.grouping}",
    ])

    # ── Resources — THIS lesson's scheme TLRs first, then activity extras ──
    # SOURCE TLRs: from the scheme for this subject + source week + indicator.
    # NEVER from another subject, another week, a static profile, or AI.
    source_tlrs: List[str] = []
    for r in list(getattr(alloc, "source_resources", []) or []):
        r = (r or "").strip()
        if r and r.lower() not in [x.lower() for x in source_tlrs]:
            source_tlrs.append(r)

    # OTHER TLRs: teacher additions for THIS lesson (from config seed on first
    # build; later owned by the lesson review object). Never merged into source.
    other_tlrs: List[str] = []
    for r in list(getattr(config, "teaching_learning_resources", []) or []):
        r = (r or "").strip()
        if r and r.lower() not in [x.lower() for x in other_tlrs]:
            other_tlrs.append(r)

    # Display union for templates that expect one TLR list.
    resources: List[str] = list(source_tlrs)
    for r in other_tlrs:
        if r.lower() not in [x.lower() for x in resources]:
            resources.append(r)
    # Subject/activity-specific support materials (deterministic, lesson-scoped).
    if act_key and interp is not None:
        for r in list(getattr(interp, "suggested_resources", []) or []) + _ACTIVITY_RESOURCES.get(act_key, []):
            r = (r or "").strip()
            if r and r.lower() not in [x.lower() for x in resources]:
                resources.append(r)

    # ── Keywords / vocabulary — content standard + exact indicator first ─
    keywords: List[str] = []
    kw_sources: List[str] = []
    # Primary derivation: content standard + exact indicator + activity context.
    kw_sources.extend(_content_terms(alloc.content_standard_description or "", limit=3))
    kw_sources.extend(_content_terms(alloc.indicator_description, limit=5))
    if act_key and interp is not None:
        kw_sources.extend(getattr(interp, "activity_keywords", []) or [])
    # Teacher-supplied terms always survive (added after derived so they stay).
    kw_sources.extend((getattr(config, "keywords", []) or []))
    kw_sources.extend(profile.keywords)
    for k in kw_sources:
        k = (k or "").strip()
        if k and k.lower() not in [x.lower() for x in keywords]:
            keywords.append(k)

    # ── Core competencies — activity-derived defaults; teacher multi-select
    # is authoritative once set on the lesson review object. ─────────────
    competencies: List[str] = []
    comp_sources = list(getattr(config, "core_competencies", []) or [])
    comp_sources.extend(_COMPETENCIES_BY_ACTIVITY.get(act_key or "demonstration", []))
    for c in comp_sources:
        c = (c or "").strip()
        if c and c.lower() not in [x.lower() for x in competencies]:
            competencies.append(c)

    # ── References — curriculum context + teacher-supplied (no invented pages)
    references: List[str] = []
    structured_refs = []
    from ..models import ReferenceEntry
    if subject_name and subject_name.strip() and subject_name.upper() != "UNKNOWN":
        structured_refs.append(ReferenceEntry(
            type="Subject Curriculum",
            title=f"{subject_name} Curriculum (NaCCA)",
            notes=f"{class_level} {subject_name}" if class_level else "",
        ))
        structured_refs.append(ReferenceEntry(
            type="Teacher's Handbook / Teacher's Guide",
            title=f"{class_level} {subject_name} Teacher's Guide",
        ))
        if alloc.strand:
            structured_refs.append(ReferenceEntry(
                type="Other",
                title=f"{subject_name} Curriculum — {alloc.strand}",
            ))
    # Teacher-supplied flat reference strings become structured Other entries
    # (pages remain blank unless the teacher supplies them explicitly).
    for ref in (getattr(config, "references", []) or []):
        ref = (ref or "").strip()
        if ref:
            structured_refs.append(ReferenceEntry(type="Other", title=ref))
    for entry in structured_refs:
        label = entry.title or entry.type
        if label and label.lower() not in [x.lower() for x in references]:
            references.append(label)

    objectives = [LearningObjective(
        # Indicator-bearing rows phrase the indicator; Nursery-style rows and
        # KG code-only rows phrase the source row's own focus (sub-strand or
        # strand). No code is attached when the source supplied none. KG rows
        # use a play-based observable verb ("explore, talk about and act out")
        # matching the source evidence: the KG1 scheme assesses through play,
        # observation and oral response, and the completed WAPEF samples phrase
        # outcomes as demonstrable actions, never board work.
        description=(
            _learner_phrase(alloc.indicator_description)
            if alloc.indicator_description and not _is_code_only(alloc.indicator_description)
            else (
                f"Learners can identify, talk about and act out "
                f"{(alloc.sub_strand or alloc.strand or 'the lesson focus').strip()}"
                if class_level in ("KG 1", "KG 2")
                else f"Learners can explore and talk about {(alloc.sub_strand or alloc.strand or 'the lesson focus').strip()}"
            )
        ),
        indicator_code=alloc.indicator_code or None,
    )]

    previous_knowledge = (
        f"Previous lesson: {prev_short}" if prev_short
        else "Learners' everyday experience related to this activity."
    )

    essential_question = _safe_format(
        _ESSENTIAL_BANK.get(act_key) or profile.essential_question, **fmt
    )

    return LessonPlan(
        scheme_of_work_id=scheme_id,
        term_config_id=config.id,
        week_number=alloc.week_number,
        week_ending=alloc.week_ending,
        week_ending_derived=bool(getattr(alloc, "week_ending_derived", False)),
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
        # Nursery-style lessons keep the source's empty indicator fields —
        # never a fabricated code or description.
        indicators=[alloc.indicator_description] if alloc.indicator_description else [],
        indicator_codes=[alloc.indicator_code] if alloc.indicator_code else [],
        lesson_topic=topic,
        essential_questions=[essential_question],
        previous_knowledge=previous_knowledge,
        keywords=keywords,
        learning_objectives=objectives,
        core_competencies=competencies,
        source_tlrs=source_tlrs,
        other_tlrs=other_tlrs,
        teaching_learning_resources=resources,
        introduction=intro,
        starter_activity=starter,
        main_activities=main_activities,
        learner_activities=learner_activities,
        teacher_activities=teacher_activities,
        assessment=assessment,
        differentiation=differentiation,
        conclusion=conclusion,
        structured_references=structured_refs,
        references=references,
        status=LessonStatus.GENERATED,
        ai_generated=False,
    )


def _learner_task(phase_name: str, skill: str) -> str:
    name = (phase_name or "").lower()
    if "demonstrat" in name or "model" in name or "explanation" in name or "teaching" in name or "predict" in name or "stimulus" in name or "inspiration" in name or "present" in name or "vocabulary" in name:
        return f"Watch and listen carefully, then describe each step of {skill} in your own words."
    if "guided" in name or "observation" in name or "practice" in name or "discussion" in name or "recording" in name or "investigation" in name or "analysis" in name or "guided writing" in name or "guided reading" in name or "comparison" in name or "first item" in name or "second item" in name or "experience" in name:
        return f"Work with your partner/group to carry out the task for {skill} and record what you find."
    if "independent" in name or "application" in name or "challenge" in name or "creation" in name or "try" in name or "comprehension" in name or "findings" in name or "sharing" in name or "accuracy" in name or "classification" in name:
        return f"Complete the task for {skill} on your own and check your work before you finish."
    if "critique" in name or "reflection" in name or "revision" in name or "improve" in name:
        return f"Look at your work on {skill}, decide what went well and what to improve."
    return f"Take an active part in the activity for {skill}."


def _teacher_move(phase_name: str, skill: str) -> str:
    name = (phase_name or "").lower()
    if "demonstrat" in name or "model" in name or "explanation" in name or "teaching" in name or "predict" in name or "stimulus" in name or "inspiration" in name:
        return f"Model {skill} slowly, think aloud, and check that all learners can see and hear."
    if "guided" in name or "observation" in name or "practice" in name or "discussion" in name or "recording" in name or "investigation" in name or "analysis" in name or "guided writing" in name or "guided reading" in name:
        return f"Move around the room, observe each group, and correct misconceptions about {skill} on the spot."
    if "independent" in name or "application" in name or "challenge" in name or "creation" in name or "try" in name or "comprehension" in name or "findings" in name or "sharing" in name or "accuracy" in name:
        return f"Circulate, give brief individual feedback, and note learners who need re-teaching of {skill}."
    if "critique" in name or "reflection" in name or "revision" in name:
        return f"Lead a short, kind critique and highlight good examples relating to {skill}."
    return f"Facilitate the activity and keep every learner focused on {skill}."

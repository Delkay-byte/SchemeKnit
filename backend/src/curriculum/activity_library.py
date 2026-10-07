"""Structured activity / teaching-evidence library (Priority 2 §5, §27).

Each entry is STRUCTURED DATA, not prose filler: it records which indicator
verbs and subjects an activity suits, what the teacher does, what learners do,
the materials it needs, the observable evidence it produces, how it is
assessed, its differentiation tiers, a timing range, which pedagogical stage
it fits (first teaching vs repeated occurrence) and — only where pedagogically
apt — a Ghanaian context framing plus a limited-resource adaptation.

Composition order enforced by the builder:

    SELECT TEACHING INTENT → ACTIVITY → LEARNER ACTION → EVIDENCE
    → RESOURCE → TIME → RENDER PROSE

No AI, no external services, no randomness: selection matches the lesson's
evidence object against these records deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class ActivityPattern:
    """One teachable activity structure and the evidence it produces."""

    id: str
    title: str
    #: Compatible indicator action verbs (lowercase).
    action_verbs: Tuple[str, ...]
    #: Subject profile keys it fits; empty = suitable for every subject.
    subjects: Tuple[str, ...] = ()
    #: Observable cognitive action this activity trains.
    cognitive_action: str = ""
    #: Templates use {focus} (indicator clause) and {concepts} (key terms).
    teacher_action: str = ""
    learner_action: str = ""
    materials: Tuple[str, ...] = ()
    #: Observable success evidence ("Look for: ...").
    evidence: str = ""
    #: Assessment sentence that measures the SAME action.
    assessment: str = ""
    #: Differentiation tiers tied to this activity.
    support: str = ""
    challenge: str = ""
    timing_range: Tuple[int, int] = (10, 30)
    #: Which occurrence stages this structure suits: "first" / "repeat".
    stages: Tuple[str, ...] = ("first", "repeat")
    #: Ghanaian framing — only listed where it genuinely adds instruction.
    ghana_context: Tuple[str, ...] = ()
    #: Bounded adaptation when resources are limited.
    adaptation: str = ""

    def fmt(self, focus: str = "", concepts: str = "") -> Dict[str, str]:
        return {"focus": focus, "concepts": concepts}


ACTIVITIES: Tuple[ActivityPattern, ...] = (
    ActivityPattern(
        id="compare_and_classify",
        title="Compare and classify",
        action_verbs=("distinguish", "compare", "classify", "categorise",
                      "categorize", "sort", "match", "select", "recognise",
                      "recognize"),
        cognitive_action="compare",
        teacher_action=("Present 3-5 concrete examples and one non-example of "
                        "{focus} and prompt learners to compare them."),
        learner_action=("Sort the examples into groups, state the rule for "
                        "each group, and justify one borderline choice."),
        materials=("sorting cards or real items", "chart", "chalkboard",
                   "exercise books"),
        evidence=("Learners classify at least 4 of 5 examples correctly and "
                  "give a reason for each classification."),
        assessment=("Classification check: give learners five mixed examples "
                    "of {focus}; they sort them and justify each group. "
                    "Success = correct groups plus one reason."),
        support=("Provide a pre-sorted partial example and a word bank of the "
                 "sorting rule for {focus}."),
        challenge=("Ask learners to invent one new example that belongs in "
                   "each group and explain why."),
        stages=("first", "repeat"),
        ghana_context=("Use familiar Ghanaian examples (market goods, local "
                       "plants, classroom objects) as the items to sort.",),
        adaptation="Use items drawn on paper/cards when real specimens are unavailable.",
    ),
    ActivityPattern(
        id="work_examples_practice",
        title="Worked example then practice",
        action_verbs=("calculate", "solve", "compute", "round", "express",
                      "determine", "apply", "use", "add", "subtract",
                      "multiply", "divide", "construct", "represent", "model"),
        subjects=("mathematics",),
        cognitive_action="apply",
        teacher_action=("Work one fully-reasoned example of {focus} on the "
                        "board, thinking aloud at each step so learners see "
                        "the method, not only the answer."),
        learner_action=("Attempt a similar problem in pairs, show every step, "
                        "then solve one independently and check the method."),
        materials=("chalkboard", "exercise books", "rulers",
                   "counting materials or number cards"),
        evidence=("Learners solve the practice problem with correct steps and "
                  "a correct answer, and can state the method."),
        assessment=("Written exercise of 2-3 problems on {focus}; mark for "
                    "correct method and correct answer. Success = correct "
                    "working, not only the result."),
        support=("Give a partially completed worked example and counting "
                 "materials so learners complete {focus} concretely first."),
        challenge=("Learners create their own problem of the same type, swap "
                   "with a partner, and solve it."),
        stages=("first", "repeat"),
        ghana_context=("Use Ghanaian market prices, cedi amounts and local "
                       "distances in the numbers.",),
        adaptation="Number lines and drawn place-value charts replace counters.",
    ),
    ActivityPattern(
        id="guided_investigation",
        title="Guided investigation",
        action_verbs=("investigate", "observe", "measure", "test", "predict",
                      "record", "examine", "research", "classify"),
        subjects=("science",),
        cognitive_action="analyse",
        teacher_action=("Set up the investigation for {focus} with locally "
                        "available materials and state the question learners "
                        "will answer."),
        learner_action=("In groups, carry out the steps, record what they "
                        "actually see in a table, and compare the result with "
                        "their prediction."),
        materials=("locally available materials", "containers",
                   "recording sheet or table", "exercise books"),
        evidence=("Groups record accurate observations in the table and their "
                  "explanation matches the recorded evidence."),
        assessment=("Observe each group against a short checklist, then ask "
                    "them to explain the result in writing. Success = "
                    "explanation supported by their own recorded data."),
        support=("Provide a partly filled recording table with sentence "
                 "starters for {focus}."),
        challenge=("Identify one variable that was not controlled and say how "
                   "they would improve the investigation."),
        stages=("first", "repeat"),
        ghana_context=("Use household or community materials and phenomena "
                       "(water, soil, local plants) for the investigation.",),
        adaptation="Observation can run with a single shared specimen demonstrated to each group.",
    ),
    ActivityPattern(
        id="demonstrate_practice",
        title="Demonstrate then supervised practice",
        action_verbs=("demonstrate", "show", "perform", "practise",
                      "practice", "install", "operate"),
        cognitive_action="apply",
        teacher_action=("Demonstrate {focus} step by step on the real object "
                        "or a labelled diagram, naming each step as it is "
                        "done and stating the safety point."),
        learner_action=("Take turns carrying out the steps themselves, naming "
                        "each step aloud, then perform the full sequence "
                        "without prompting."),
        materials=("the real apparatus or an unplugged model", "chart",
                   "chalkboard", "exercise books"),
        evidence=("Each learner performs the full sequence of {focus} "
                  "correctly, in order, with no missing step."),
        assessment=("Observable performance: each learner (or pair) performs "
                    "{focus} once while the teacher ticks a step checklist. "
                    "Success = all steps completed in the correct order."),
        support=("Give a numbered step card and one guided rehearsal before "
                 "the solo attempt."),
        challenge=("Learners spot and correct one deliberate error the teacher "
                   "introduces, then explain the correct step."),
        stages=("first", "repeat"),
        adaptation=("An unplugged model, drawing or diagram stands in when "
                    "the real device or apparatus is shared.",),
    ),
    ActivityPattern(
        id="model_language_use",
        title="Model then guided communicative use",
        action_verbs=("use", "ask", "respond", "participate", "read", "write",
                      "pronounce", "recite", "describe", "explain"),
        subjects=("english",),
        cognitive_action="apply",
        teacher_action=("Model the target language for {focus} in a short "
                        "contextual exchange, highlighting the feature "
                        "learners must use."),
        learner_action=("Practise the form in guided pairs, then use it in a "
                        "short communicative task with their own content."),
        materials=("conversation or prompt cards", "chalkboard",
                   "exercise books", "reader or story text"),
        evidence=("In the communicative task learners use the target feature "
                  "correctly at least twice and stay intelligible."),
        assessment=("Short communicative performance: pairs hold an exchange "
                    "using {focus}; teacher ticks correct uses and notes one "
                    "common error to address."),
        support=("Provide a word bank and a sentence frame for the exchange."),
        challenge=("Learners extend the exchange with two unplanned turns and "
                   "switch between formal and informal register."),
        stages=("first", "repeat"),
        ghana_context=("Use familiar Ghanaian names, family and community "
                       "situations as the content of the exchange.",),
        adaptation="Prompts can be written on the board; no printed cards needed.",
    ),
    ActivityPattern(
        id="design_create",
        title="Design and create",
        action_verbs=("design", "create", "make", "draw", "compose",
                      "construct", "build"),
        subjects=("creative_arts", "career_technology"),
        cognitive_action="create",
        teacher_action=("Present two contrasting examples of {focus} and "
                        "briefly name the criteria that make each work."),
        learner_action=("Sketch a plan, produce the artifact or performance "
                        "using local materials, and state two reasons their "
                        "design meets the criteria."),
        materials=("local materials for making", "manila paper", "glue or "
                   "thread", "display space"),
        evidence=("The finished work applies the stated criteria and the "
                  "learner can justify two design choices."),
        assessment=("Assess the product against a short rubric (criteria met, "
                    "neatness/technique, effort) plus a one-sentence "
                    "justification by the learner."),
        support=("Provide a partially completed example and a checklist of "
                 "the criteria."),
        challenge=("Improve the work after peer feedback and explain which "
                   "change improved it."),
        stages=("first", "repeat"),
        ghana_context=("Draw on local craft and design examples (kente, "
                       "adinkra, local pottery, household objects).",),
        adaptation="Use waste paper, cloth scraps, seeds and leaves instead of bought materials.",
    ),
    ActivityPattern(
        id="explain_justify",
        title="Explain and justify",
        action_verbs=("explain", "analyse", "analyze", "evaluate", "justify",
                      "discuss", "examine", "interpret", "compare"),
        cognitive_action="analyse",
        teacher_action=("Elicit an initial explanation of {focus} with one "
                        "question, then supply the key evidence or example "
                        "that sharpens it."),
        learner_action=("Give a reasoned explanation in pairs, support it "
                        "with one piece of evidence, and revise it after "
                        "feedback."),
        materials=("chart or source extract", "chalkboard", "exercise books"),
        evidence=("The explanation names the correct ideas about {focus} and "
                  "is backed by at least one piece of evidence or reason."),
        assessment=("Ask for a short written or oral explanation of {focus} "
                    "with one supporting reason. Success = accurate idea plus "
                    "supporting evidence."),
        support=("Provide a structured frame: '… because …' plus two key "
                 "words from the lesson."),
        challenge=("Evaluate an opposing view and say what evidence would "
                   "change their mind."),
        stages=("first", "repeat"),
        ghana_context=("Use Ghanaian community or national examples as the "
                       "cases learners explain.",),
        adaptation="Discussion can run as think-pair-share without any printed material.",
    ),
    ActivityPattern(
        id="identify_recognise",
        title="Identify and state",
        action_verbs=("identify", "name", "list", "state", "outline",
                      "recall", "research"),
        cognitive_action="remember",
        teacher_action=("Present the item set for {focus} and elicit names or "
                        "features from learners before confirming."),
        learner_action=("Name or list the items/features of {focus} from "
                        "memory, then check against the board and correct "
                        "their own work."),
        materials=("picture cards or real items", "chalkboard",
                   "exercise books"),
        evidence=("Learners name the required items or features of {focus} "
                  "with at least 4 of 5 correct."),
        assessment=("Quick oral or written check: learners name/list the "
                    "elements of {focus}. Success = 4 of 5 correct with no "
                    "prompted answers."),
        support=("Give a word bank or labelled diagram to choose from."),
        challenge=("State the items without prompts and add one example the "
                   "lesson did not cover."),
        stages=("first", "repeat"),
        adaptation="Draw the items on the board when no cards or specimens exist.",
    ),
    ActivityPattern(
        id="role_play_practice",
        title="Role play then reflect",
        action_verbs=("role play", "perform", "participate", "demonstrate",
                      "create", "act"),
        subjects=("rme", "phe", "social_studies"),
        cognitive_action="apply",
        teacher_action=("Set the short scenario for {focus} and model the "
                        "expected behaviour or movement once."),
        learner_action=("Act out the scenario in small groups, then reflect "
                        "on what the performance shows about {focus}."),
        materials=("open space", "simple props", "chalkboard"),
        evidence=("Groups perform the scenario accurately and one learner "
                  "states what it shows about {focus}."),
        assessment=("Observe the performance against three agreed criteria "
                    "and ask each group for one reflection point."),
        support=("Give group members a short script or cue card."),
        challenge=("Adapt the scenario to a new situation and perform it "
                   "without preparation."),
        stages=("first", "repeat"),
        ghana_context=("Base the scenario on everyday Ghanaian family and "
                       "community life.",),
        adaptation="Needs no materials beyond the classroom space.",
    ),
)


_BY_VERBS: Dict[str, List[ActivityPattern]] = {}
for _a in ACTIVITIES:
    for _v in _a.action_verbs:
        _BY_VERBS.setdefault(_v, []).append(_a)


def select_activity(
    verbs: Sequence[str],
    subject_key: str = "",
    stage: str = "first",
    activity_type: str = "",
) -> ActivityPattern:
    """Deterministic activity selection from the lesson's own evidence.

    Scores candidate activities by verb overlap with the indicator's action
    verbs, subject fit and occurrence stage; ties break on library order.
    Never random — the same evidence always selects the same activity.
    """
    best: Optional[ActivityPattern] = None
    best_score = 0.0
    verb_list = [str(v).strip().lower() for v in verbs if str(v).strip()]
    hint = (activity_type or "").lower().replace(" ", "_")
    for activity in ACTIVITIES:
        score = 0.0
        for v in verb_list:
            if v in activity.action_verbs:
                score += 2.0
            elif any(v.startswith(av) or av.startswith(v)
                     for av in activity.action_verbs if len(av) >= 4):
                score += 1.0
        if subject_key and activity.subjects:
            score += 3.0 if subject_key in activity.subjects else -1.0
        if hint and hint in activity.id:
            score += 1.5
        if stage and stage not in activity.stages:
            score -= 0.5
        if score > best_score:
            best_score = score
            best = activity
    if best is None:
        best = ACTIVITIES[0]
    return best


# ── Verb-matched assessment guarantees (Priority 2 §15) ─────────────────────
#
# Assessment must measure the indicator's OWN action. These bounded sentences
# are appended only when the composed assessment does not already contain the
# indicator's verb stem — never stacked, never replacing the activity check.

ASSESSMENT_FOR_VERB: Dict[str, str] = {
    "distinguish": ("Check: learners sort or separate paired examples of "
                    "{focus} and give one reason for each choice."),
    "compare": ("Check: learners complete a comparison of {focus} (two "
                "similarities, two differences) and state one conclusion."),
    "classify": ("Check: learners classify a fresh set of items for "
                 "{focus} and state the rule they used."),
    "categorise": ("Check: learners categorise a fresh set of items for "
                   "{focus} and state the rule they used."),
    "calculate": ("Check: learners calculate one unseen item for {focus} "
                  "showing full working."),
    "solve": ("Check: learners solve one unseen problem on {focus} and show "
              "each step of the method."),
    "round": ("Check: learners round one unseen number for {focus} and state "
              "the place they rounded to."),
    "demonstrate": ("Check: each learner demonstrates {focus} once against a "
                    "short step checklist."),
    "perform": ("Check: each learner performs {focus} once against three "
                "agreed criteria."),
    "design": ("Check: learners produce a design for {focus} that meets two "
               "stated criteria and justify one choice."),
    "create": ("Check: learners create their own example of {focus} and "
               "justify how it meets the criteria."),
    "explain": ("Check: learners give a short explanation of {focus} with "
                "one supporting reason or piece of evidence."),
    "analyse": ("Check: learners analyse the given source for {focus} and "
                "state one pattern with supporting evidence."),
    "evaluate": ("Check: learners give a judgement on {focus} with one "
                 "reason drawn from the evidence."),
    "justify": ("Check: learners justify one decision about {focus} with "
                "two reasons."),
    "describe": ("Check: learners describe {focus} in their own words using "
                 "at least three key terms correctly."),
    "identify": ("Check: learners identify the elements of {focus} in a new "
                 "example, unprompted."),
    "compare_": "",
}


def assessment_for_verb(verb: str, focus: str) -> str:
    """The verb-matched assessment sentence, or "" when none applies."""
    key = (verb or "").strip().lower()
    template = ASSESSMENT_FOR_VERB.get(key, "")
    if not template:
        return ""
    return template.format(focus=focus)


# ── Ghanaian context bank (Priority 2 §13) ──────────────────────────────────
#
# Used only where the framing adds instruction. One bounded clause per lesson,
# keyed by subject — never sprinkled into every sentence.

GHANA_CONTEXT_BY_SUBJECT: Dict[str, Tuple[str, ...]] = {
    "mathematics": ("Use Ghanaian market prices, cedi amounts and local "
                    "distances as the numbers in the examples.",),
    "science": ("Use locally available household and community materials "
                "for the observation or investigation.",),
    "english": ("Set the exchange in familiar Ghanaian family and community "
                "situations so the language use stays meaningful.",),
    "ict": ("Where devices are shared, use the unplugged steps first "
            "and let every learner touch the real device once.",),
    "creative_arts": ("Draw the design examples from local craft — kente, "
                      "adinkra, pottery, household objects.",),
    "social_studies": ("Anchor the discussion in Ghanaian community and "
                       "national examples learners know first.",),
    "rme": ("Use everyday Ghanaian family and community situations as the "
            "cases for the value discussed.",),
    "phe": ("Use local games, playground activities and everyday physical "
            "tasks as the practice context.",),
    "career_technology": ("Use local tools, materials and trades learners "
                          "see in their community.",),
}


def ghana_context_for(subject_key: str) -> str:
    """One apt Ghanaian context framing for this subject, or ""."""
    for key, options in GHANA_CONTEXT_BY_SUBJECT.items():
        if subject_key == key or subject_key.startswith(key):
            return options[0] if options else ""
    return ""


def concept_list(text: str, limit: int = 4) -> List[str]:
    return [w for w in str(text or "").split()[:limit]]

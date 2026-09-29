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
from datetime import date
from typing import Dict, List, Optional, Tuple

from ..models import (
    AllocatedIndicator, TermConfig, LessonPlan, LessonStatus, Subject,
    ClassLevel, LearningObjective, TeachingActivity,
)
from .pedagogy import profile_for_subject, SubjectPedagogy
from ..ai_resource_text import normalize_text_items

#: Layer 3/4 integration — imported lazily inside ``build_lesson`` to avoid an
#: import cycle (patterns imports nothing from the builder; the typing-only
#: names below are for signatures and annotations).
from typing import TYPE_CHECKING
if TYPE_CHECKING:  # pragma: no cover
    from .patterns import LessonPattern
    from .variation import BatchHistory

#: The canonical code patterns live in the curriculum package so the builder,
#: the allocation engine and every template renderer agree on what a code is.
from . import CODE_PREFIX_RE as _CODE_RE  # noqa: E402

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
    # Relations/pronouns that carried no vocabulary value into a keyword list.
    "between", "within", "through", "across", "among", "about", "also",
    "both", "each", "other", "others", "more", "most", "same", "involving",
    "involve", "involves", "him", "her", "his", "he", "she", "we", "our",
    "us", "you", "your", "they", "i", "ways", "way",
}

#: Bloom action verbs (PART 14). They say what learners DO, not what the
#: lesson is ABOUT, so they are not vocabulary: repeating "distinguish",
#: "compare", "discuss" in every keyword list was the reported defect.
_BLOOM_ACTION_WORDS = {
    "identify", "recognise", "recognize", "summarise", "summarize",
    "interpret", "classify", "compare", "contrast", "paraphrase",
    "illustrate", "exemplify", "clarify", "demonstrate", "solve",
    "calculate", "perform", "execute", "implement", "construct", "build",
    "draw", "record", "measure", "complete", "practice", "practise",
    "analyse", "analyze", "examine", "investigate", "differentiate",
    "distinguish", "categorise", "categorize", "organise", "organize",
    "determine", "evaluate", "assess", "judge", "justify", "critique",
    "review", "argue", "defend", "recommend", "decide", "select",
    "choose", "rate", "design", "produce", "plan", "compose",
    "formulate", "generate", "develop", "compute", "find", "prepare",
    "sort", "group", "state", "name", "label", "match", "list",
    "describe", "explain", "discuss", "define", "read", "write",
    "observe", "apply", "show", "give", "take", "make", "create",
    # Arithmetic operations: the lesson's own noun ("addition", "fractions")
    # is the vocabulary, not the command.
    "add", "subtract", "multiply", "divide", "sum", "simplify", "convert",
}

#: Multi-word generic activity phrases the interpreter supplies as action
#: context — useful for selecting a phase, never useful as lesson vocabulary.
_KEYWORD_NOISE = {
    "share views", "sharing ideas", "talk about", "talk", "debate",
    "ideas", "things", "stuff", "activity", "activities",
}

# ── Indicator-activity phase banks ─────────────────────────────────────────
# Each entry is (phase_name, template). Templates may use {focus},
# {focus_short}, {verb}, {resource}, {strand}, {sub_strand}, {skill},
# {topic}, {bloom}, {evidence}, {class_level}.
# The bank is keyed by the indicator's activity type so a problem-solving
# lesson and an investigation lesson do not share one skeleton.

#: How THIS subject puts the activity into practice (PART 17). The shared
#: activity banks select the structure from the indicator's verb; this sentence
#: is appended to the MAIN block's consolidating phase so the same verb is
#: taught the way the subject actually does it — a discussion in RME and a
#: discussion in Mathematics no longer share one identical skeleton. One
#: bounded sentence per subject, never a subject-sized prompt.
_SUBJECT_PRACTICE_CLAUSE: Dict[str, str] = {
    "mathematics": (
        "Insist on the full working, not only the answer, and link the numbers "
        "to a real Ghanaian context learners can picture."
    ),
    "science": (
        "Base every answer on what was actually observed or measured, and keep "
        "the recording in a simple labelled table."
    ),
    "english": (
        "Require the target language features and support every point with "
        "evidence from the text or the learner's own experience."
    ),
    "social_studies": (
        "Connect the idea to people, places and decisions in the learners' own "
        "community."
    ),
    "creative_arts": (
        "Work with the correct technique and locally available materials, and "
        "judge the work against a simple shared criteria list."
    ),
    "ict": (
        "Handle the real device or a labelled diagram of it, and name each part "
        "with its correct term while using it."
    ),
    "rme": (
        "Give reasons respectfully, listen to a different view, and connect the "
        "idea to how learners should live and relate to others."
    ),
    "phe": (
        "Keep the body position safe and controlled, and let every learner take "
        "an active turn rather than watch."
    ),
    "career_technology": (
        "Follow the correct procedure in order, observe the safety rules for the "
        "tools, and inspect the finished product against them."
    ),
    "early_childhood": (
        "Keep the activity playful and concrete: movement, song or real objects, "
        "with the teacher observing what each child can do."
    ),
    "nursery": (
        "Keep the activity playful and concrete, and assess by watching what "
        "each child does with the real objects."
    ),
}

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

#: Learner-activity templates keyed by activity type — what LEARNERS do in
#: each phase. Parallel to ``_PHASE_BANK`` (which describes the teacher's
#: action) so the learner column is equally specific: a classification lesson
#: has learners sorting and justifying, an investigation has learners
#: recording evidence. This replaces the generic "Watch and listen carefully"
#: / "Complete the task" fallbacks with concrete, indicator-tied actions.
_LEARNER_PHASE_BANK: Dict[str, List[Tuple[str, str]]] = {
    "problem_solving": [
        ("Worked example",
         "Follow the worked example for {focus_short} on the board, noting each "
         "step and the reason for it."),
        ("Guided practice",
         "In mixed-ability pairs, solve a parallel problem on {focus_short}, "
         "explaining each step to your partner."),
        ("Independent practice",
         "Solve two problems on {focus_short} alone, then check your method "
         "against the board."),
    ],
    "investigation": [
        ("Prediction",
         "Record your prediction about {focus_short} and the reason for it "
         "before starting."),
        ("Investigation",
         "Carry out the activity for {focus_short} in your group using "
         "{resource}, recording what you observe or measure."),
        ("Explanation",
         "Explain how your group's evidence supports or contradicts your "
         "prediction about {focus_short}."),
    ],
    "practical": [
        ("Demonstration",
         "Watch the demonstration of {focus_short} and note the order of steps "
         "and the safety points."),
        ("Guided practical",
         "Carry out the practical task for {focus_short} in your group using "
         "{resource}, following the demonstrated steps."),
        ("Application",
         "Complete one task on {focus_short} and inspect your own product "
         "against the steps."),
    ],
    "classification": [
        ("Presentation of examples",
         "Examine the two contrasting examples for {focus_short} and identify "
         "what is the same and what is different."),
        ("Classification activity",
         "Sort or group the given items by the rule for {focus_short}, "
         "explaining the basis of each group."),
        ("Accuracy check",
         "Review the class groups, challenge one borderline item and agree "
         "the correct classification for {focus_short}."),
    ],
    "observation": [
        ("Directed observation",
         "Observe {focus_short} closely, focusing on the features the teacher "
         "points out."),
        ("Recording",
         "Record your observations of {focus_short} in a simple table or "
         "labelled diagram using the correct terms."),
        ("Discussion of findings",
         "Compare your observations with other groups and identify the key "
         "pattern about {focus_short}."),
    ],
    "reading": [
        ("Vocabulary and preview",
         "Learn the key words for {focus_short} and preview the text, "
         "predicting its content from the title."),
        ("Guided reading",
         "Read the text for {focus_short} together, underlining evidence "
         "relevant to the indicator."),
        ("Comprehension task",
         "Answer comprehension questions on {focus_short}, giving evidence "
         "from the text."),
    ],
    "writing": [
        ("Model text",
         "Study the model showing how {focus_short} is done and note the "
         "features to reproduce."),
        ("Guided writing",
         "Plan and draft your own piece for {focus_short} using the model as "
         "a scaffold."),
        ("Independent writing",
         "Complete and improve your piece on {focus_short} against a short "
         "checklist."),
    ],
    "discussion": [
        ("Stimulus",
         "Examine the scenario or question about {focus_short} and identify "
         "the key issue involved."),
        ("Structured discussion",
         "Take part in the group discussion on {focus_short}, giving reasons "
         "and responding to other views."),
        ("Application",
         "Apply the discussion to a local situation and answer 'what would we "
         "do here?' about {focus_short}."),
    ],
    "comparison": [
        ("First item",
         "Examine the first item for {focus_short} and note its features."),
        ("Second item",
         "Examine the second item and note how it differs for {focus_short}."),
        ("Comparison task",
         "Complete a comparison chart for {focus_short}, stating the "
         "similarities and differences clearly."),
    ],
    "creation": [
        ("Inspiration",
         "Examine the sample connected to {focus_short} and notice how it was "
         "made or performed."),
        ("Creation",
         "Create your own work applying {focus_short}, using {resource}."),
        ("Critique and revision",
         "Display or perform your work, give kind specific feedback on "
         "{focus_short}, then revise."),
    ],
    "analysis": [
        ("Present data/source",
         "Examine the data or source linked to {focus_short} and check you "
         "understand what it shows."),
        ("Analysis",
         "Break down the information for {focus_short}, identifying patterns, "
         "causes or relationships."),
        ("Findings",
         "Report your group's findings about {focus_short} and agree the key "
         "conclusion."),
    ],
    "reflection": [
        ("Experience review",
         "Recall the experience or learning linked to {focus_short} and "
         "identify what stood out."),
        ("Reflection task",
         "Reflect on {focus_short} in writing, justifying what you would keep "
         "or change."),
        ("Sharing",
         "Share your reflections about {focus_short} and identify the main "
         "lesson."),
    ],
    "demonstration": [
        ("Teacher demonstration",
         "Watch the demonstration of {focus_short} and note each step and the "
         "reason for it."),
        ("Guided imitation",
         "Repeat or reproduce the demonstration for {focus_short} with the "
         "teacher's prompts, using {resource}."),
        ("Independent application",
         "Perform the task for {focus_short} on your own and check your work "
         "against the demonstrated steps."),
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

#: CLASS ASSIGNMENT templates keyed by activity type (PART 15): the task the
#: class completes IN the lesson, aligned to the indicator's own action — a
#: classification indicator gets a sorting task, an investigation gets an
#: evidence-recording task. Never a generic written question for every lesson.
_CLASS_ASSIGNMENT_BANK: Dict[str, str] = {
    "problem_solving": (
        "In pairs, learners work through two problems on {focus_short} in their "
        "exercise books. The teacher moves round, checks each pair's method and "
        "asks one pair to explain their reasoning to the class."
    ),
    "investigation": (
        "Groups carry out the investigation into {focus_short} and record what "
        "they observe in a table. The teacher checks that each group records "
        "what they actually saw, not what they expected."
    ),
    "practical": (
        "In groups, learners carry out the practical task for {focus_short}, "
        "following the demonstrated steps. The teacher observes technique and "
        "safety and gives short corrective feedback as they work."
    ),
    "classification": (
        "Pairs sort or group the given items by the rule for {focus_short} and "
        "write one reason for each group. The teacher checks a sample and asks "
        "two pairs to justify a borderline item."
    ),
    "observation": (
        "Learners observe {focus_short} and record their findings in a simple "
        "labelled table, using the correct terms. The teacher checks the "
        "accuracy of the recorded terms."
    ),
    "reading": (
        "Learners read the passage on {focus_short} and answer the "
        "comprehension questions, giving evidence from the text. The teacher "
        "checks the answers of three learners and corrects one common error."
    ),
    "writing": (
        "Learners draft their own piece on {focus_short} using the model as a "
        "scaffold. The teacher circulates, corrects one shared error and asks "
        "two learners to read their opening sentence aloud."
    ),
    "discussion": (
        "Groups discuss the question on {focus_short} and prepare two reasons "
        "for their position. Each group presents for one minute and the "
        "teacher records the strongest points on the board."
    ),
    "comparison": (
        "Learners complete a comparison chart for {focus_short}, listing the "
        "similarities and differences. The teacher checks three charts against "
        "the class model."
    ),
    "creation": (
        "Learners create their own work applying {focus_short}, using locally "
        "available materials. The teacher observes technique and gives short "
        "feedback while they work."
    ),
    "analysis": (
        "Learners analyse the data or source for {focus_short} and write the "
        "pattern they find with one piece of supporting evidence. The teacher "
        "checks the reasoning, not just the answer."
    ),
    "reflection": (
        "Learners write a short reflection on {focus_short}, stating what they "
        "would keep and what they would change. The teacher reviews a sample "
        "and gives feedback."
    ),
    "demonstration": (
        "In groups, learners demonstrate the task for {focus_short} while the "
        "teacher observes and records which learners have met the indicator."
    ),
}

#: HOME ASSIGNMENT templates keyed by activity type (PART 15): a genuine
#: follow-up the learner can complete away from school, reusing the lesson's
#: own focus. A practical lesson is never forced into a written homework
#: question, and an investigation gets an observation task instead.
_HOME_ASSIGNMENT_BANK: Dict[str, str] = {
    "problem_solving": (
        "Write and solve three short problems of the same type as today's work "
        "on {focus_short}. Show each step clearly."
    ),
    "investigation": (
        "Find one more example of {focus_short} at home or in your community "
        "and write what you observed and what it shows."
    ),
    "practical": (
        "Practise the steps for {focus_short} at home where it is safe to do "
        "so, and write down the steps you followed."
    ),
    "classification": (
        "Collect or draw five items you can group and write the rule you used "
        "to group them for {focus_short}."
    ),
    "observation": (
        "Observe something related to {focus_short} at home and record three "
        "things you notice in your exercise book."
    ),
    "reading": (
        "Read the text on {focus_short} again and write three sentences about "
        "the main idea."
    ),
    "writing": (
        "Write a short paragraph on {focus_short}, using at least three of "
        "today's key words."
    ),
    "discussion": (
        "Ask one adult at home about {focus_short} and write two points you "
        "learned from the conversation."
    ),
    "comparison": (
        "Draw a table comparing two things related to {focus_short} and list "
        "one similarity and one difference."
    ),
    "creation": (
        "Finish or improve the work you started today on {focus_short} and "
        "bring it to the next lesson."
    ),
    "analysis": (
        "Find one more example of {focus_short} at home and write what it "
        "shows."
    ),
    "reflection": (
        "Write three sentences about what you learned in {focus_short} and how "
        "you will use it at home."
    ),
    "demonstration": (
        "Practise the steps for {focus_short} at home and be ready to show one "
        "step in the next lesson."
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


# ── Pattern rendering (Layer 3 integration) ────────────────────────────────
#
# The lesson pattern supplies the teaching SEQUENCE; these banks supply the
# concrete classroom wording for each pattern moment. The starter modulates
# HOW the lesson opens and the plenary HOW it closes, so a batch of lessons
# on different indicators does not all open and end with the same sentence
# skeleton. All templates are rendered with the existing ``fmt`` placeholders
# so the indicator remains visibly the subject of every sentence.

#: STARTER MODES (Layer 3/4): the pattern's opening moment. Each names a
#: concrete teacher action and learner action, never "discuss the previous
#: lesson". Selected from the pattern's ``starter_mode``.
STARTER_MODE_TEMPLATES: Dict[str, str] = {
    "retrieval": (
        "Quick recall: ask three learners to state what they remember about "
        "{focus_short} from the last lesson. Write one keyword on the board "
        "and have the class read it together."
    ),
    "object_observation": (
        "Show a real object or a picture connected to {focus_short} and ask "
        "learners to say three things they notice about it before any "
        "explanation."
    ),
    "quick_scenario": (
        "Tell a one-minute local scenario about {focus_short} (a market, home "
        "or community situation) and ask: 'what would you do here, and why?'"
    ),
    "diagnostic_question": (
        "Pose one diagnostic question about {focus_short} and ask for hands; "
        "note who answers confidently and who hesitates — this frames the "
        "support needed today."
    ),
    "demonstration_teaser": (
        "Perform the first step of {focus_short} without explaining it and "
        "ask learners to predict what you will do next and why."
    ),
    "prior_knowledge_challenge": (
        "Write one statement about {focus_short} on the board that is ALMOST "
        "right, and challenge the class to find what is wrong with it."
    ),
    "misconception_probe": (
        "Present the common mistake around {focus_short} as if it were a "
        "learner's answer, and ask the class whether they agree and why."
    ),
    "short_game": (
        "Play a quick two-minute game around {focus_short} — thumbs up/down "
        "or a call-and-response — so every learner answers at least once."
    ),
    "prediction": (
        "Ask learners to predict what will happen with {focus_short}: record "
        "two or three predictions on the board without judging them yet."
    ),
    "oral_classification": (
        "Say aloud four items linked to {focus_short} and ask learners to "
        "tell you which two belong together and why."
    ),
    "real_life_connection": (
        "Ask learners to name where they have seen {focus_short} at home or "
        "in their community; collect two examples on the board."
    ),
    "vocabulary_activation": (
        "Build a quick word wall for {focus_short}: learners say the key "
        "words they already know, and the teacher adds the two they will need "
        "today."
    ),
    "contrast_pairs": (
        "Show two contrasting examples linked to {focus_short} and ask "
        "learners to name one way they are the same and one way they differ."
    ),
    "warm_up_game": (
        "Lead a lively warm-up game or action song connected to {focus_short}, "
        "then settle the class and state today's focus."
    ),
}

#: PLENARY MODES (Layer 3/4): the pattern's closing moment. Each must produce
#: EVIDENCE that learners understood the objective, never a bare 'review'.
PLENARY_MODE_TEMPLATES: Dict[str, str] = {
    "exit_question": (
        "Exit question: every learner answers one question on {focus_short} "
        "in their book or orally before leaving; use the answers to plan "
        "re-teaching."
    ),
    "learner_explanation": (
        "Ask two learners to explain {focus_short} to the class in their own "
        "words, and ask one other learner whether they agree."
    ),
    "quick_classification": (
        "Give three examples and one non-example of {focus_short} and ask the "
        "class to identify the one that does not belong and why."
    ),
    "one_minute_summary": (
        "One-minute summary: each learner writes one sentence about "
        "{focus_short}; two read theirs aloud and the class agrees the best "
        "statement."
    ),
    "teach_a_peer": (
        "Each learner teaches {focus_short} to a partner in one minute; the "
        "teacher listens in and names one strong explanation."
    ),
    "application_scenario": (
        "Give one real-life scenario about {focus_short} and ask learners to "
        "say what they would do and why; two or three answer."
    ),
    "misconception_correction": (
        "Return to any prediction or misconception about {focus_short} from "
        "the starter and correct it together, naming what the evidence "
        "showed."
    ),
    "oral_recap": (
        "Oral recap: the teacher asks, learners answer in chorus for the key "
        "facts, then one learner summarises {focus_short} in a sentence."
    ),
    "demonstration": (
        "Ask two learners to demonstrate {focus_short} while the class checks "
        "each step; correct one common error together."
    ),
    "reflection_question": (
        "Reflection question: learners write one thing they can now do with "
        "{focus_short} and one question they still have."
    ),
    "retrieval_challenge": (
        "Quick retrieval challenge: three rapid questions on {focus_short} "
        "covering the starter, the main practice and one extension; keep a "
        "tally of confident answers."
    ),
    "explain_rule": (
        "Ask learners to state the rule or method for {focus_short} in one "
        "sentence, then give one new example that fits it."
    ),
    "justify_choice": (
        "Ask learners to justify one choice they made about {focus_short} "
        "today and to name one difference it made."
    ),
    "report_findings": (
        "Two groups report their findings on {focus_short}; the class agrees "
        "the strongest evidence and one open question."
    ),
    "conclusion_check": (
        "Ask the class to answer the question that opened the lesson about "
        "{focus_short}, and to explain how their evidence supports the answer."
    ),
    "group_presentation_recap": (
        "Each group presents its analysis of {focus_short} in one minute; the "
        "teacher records the strongest reason and one disagreement."
    ),
    "application_commitment": (
        "Each learner names one way they will apply {focus_short} this week "
        "in their home or community; two or three share with the class."
    ),
    "share_and_critique": (
        "Three learners display or perform their work on {focus_short}; the "
        "class gives one kind, specific point of feedback each."
    ),
    "cool_down_reflection": (
        "Cool down with gentle movement, then ask learners to name the most "
        "important technique or safety point about {focus_short} they "
        "practised today."
    ),
    "misconception_correction": (
        "Return to any prediction or misconception about {focus_short} from "
        "the starter and correct it together, naming what the evidence "
        "showed."
    ),
}

#: Weight of each pattern-step ROLE inside the MAIN block (fractions of the
# main period). Kept close to the established profile weighting so a pattern's
# rhythm still respects the standard lesson shape.
_STEP_ROLE_WEIGHTS: Dict[str, float] = {
    "input": 0.30,
    "guided": 0.40,
    "independent": 0.20,
    "synthesis": 0.30,
}


def _render_pattern_step(step, fmt: Dict[str, str], profile, act_key):
    """Render ONE pattern step as (name, description, weight).

    The step's activity bank supplies the shared classroom skeleton; when the
    subject's own pedagogy (Layer 2) has a MOVE for the step's role or
    activity key, the step is rendered through that move instead — so one
    pattern reads differently in Computing, Mathematics and RME. Fallbacks
    keep the step fully specified: a pattern step is never rendered as a bare
    heading.
    """
    from .pedagogy import subject_move
    from .patterns import PatternStep

    if not isinstance(step, PatternStep):
        return None

    weight = _STEP_ROLE_WEIGHTS.get(step.role, 0.25)

    # 1. INDICATOR-FOLLOWING steps: the indicator's OWN activity bank is the
    #    canonical classroom structure for this curriculum work — a
    #    Mathematics problem_solving indicator keeps its worked example +
    #    practice, an investigation keeps prediction → investigate → explain.
    #    The pattern sequences AROUND the core practice; it never rewrites it.
    if step.use_indicator_activity and act_key:
        bank = _PHASE_BANK.get(act_key) or []
        if bank:
            idx = 0 if step.role == "input" else (
                1 if step.role == "guided" else min(len(bank) - 1, 2))
            tmpl = bank[min(idx, len(bank) - 1)][1]
            desc = _safe_format(tmpl, **fmt)
            if desc.strip():
                return (step.name, desc, weight)

    # 2. Subject moves (Layer 2): the subject's own way of doing the step's
    #    activity, so one pattern reads differently across subjects.
    move = subject_move(profile.key, step.activity_key)
    if move is None:
        move = subject_move(profile.key, step.role)
    if move is None and act_key and act_key != step.activity_key:
        move = subject_move(profile.key, act_key)
    if move is None:
        move = subject_move("generic", step.role) or subject_move(
            "generic", step.activity_key)

    if move:
        desc = _safe_format(move, **fmt)
    else:
        # 3. Shared activity bank for the step's own activity key.
        bank = _PHASE_BANK.get(step.activity_key) or _PHASE_BANK.get(
            act_key or "") or []
        if bank:
            idx = 0 if step.role == "input" else (
                1 if step.role == "guided" else min(len(bank) - 1, 2))
            tmpl = bank[min(idx, len(bank) - 1)][1]
            desc = _safe_format(tmpl, **fmt)
        else:
            desc = _safe_format(
                "Carry out {focus_short} following the demonstrated steps.", **fmt)

    if not desc.strip():
        desc = _safe_format(
            "Carry out {focus_short} following the demonstrated steps.", **fmt)

    return (step.name, desc, weight)


def strip_indicator_code(text: str) -> str:
    """Remove a leading curriculum code (e.g. B7.4.3.1.2) from indicator text."""
    if not text:
        return ""
    return _CODE_RE.sub("", text).strip() or text.strip()


from . import ANY_CODE_RE as _ANY_CODE_RE  # noqa: E402


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
    """Best-effort subject/indicator interpretation (never fatal).

    Indicatorless rows (Nursery week-units) are interpreted from the row's OWN
    curriculum text (sub-strand + strand) when the indicator cell is empty: the
    sub-strand names what the lesson actually does ("Sorting and matching",
    "Tracing", "Colouring"), so activity typing still follows the source
    instead of defaulting every Nursery lesson to one skeleton. No curriculum
    code is invented — the row text is used only to READ the activity type.
    """
    try:
        from .indicator_interpreter import interpret_indicator
        from . import Indicator
        description = alloc.indicator_description or ""
        if not description.strip():
            description = " ".join(
                part for part in (alloc.sub_strand, alloc.strand) if part
            ).strip()
        ind = Indicator(
            code=alloc.indicator_code or "",
            exact_text=f"{alloc.indicator_code or ''} {description}".strip(),
            description=description,
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
    position_index: int = 0,
) -> List[Tuple[str, str, float]]:
    """Return (phase_name, description, weight) for the MAIN block.

    Structure follows the indicator's actual activity type when it is
    genuinely expressed; otherwise the subject profile's own pedagogy supplies
    the phases (mathematics: worked example → practice; science: inquiry;
    English: model → production).

    ``position_index`` is the lesson's position in its teaching week (0 = the
    week's first lesson of that subject). A class-teacher week may teach the
    same curriculum focus on several days, so a later position composes its
    MAIN block from the week's other available structure — the subject
    profile's phases when the first day used the indicator's activity phases,
    and vice versa — and rotates within it. That keeps each day's MAIN work
    genuinely different while using only the pedagogy data that already exists:
    no new curriculum content is invented, and position 0 is byte-identical to
    the established single-lesson output.
    """
    bank: List[Tuple[str, str, float]] = []
    if act_key:
        phase_bank = _PHASE_BANK.get(act_key)
        if phase_bank:
            base = [0.30, 0.40, 0.30]
            if len(phase_bank) == 4:
                base = [0.25, 0.30, 0.30, 0.15]
            for i, (name, tmpl) in enumerate(phase_bank):
                weight = base[i] if i < len(base) else 0.25
                bank.append((name, _safe_format(tmpl, **fmt), weight))

    profile_phases = [
        (mp.name, _safe_format(mp.template, **fmt), mp.weight)
        for mp in profile.main_phases
    ]

    # PART 17: make the indicator's activity skeleton subject-specific. The
    # consolidating phase carries this subject's own practice sentence so the
    # same verb is never taught with an identical template in every subject.
    clause = _SUBJECT_PRACTICE_CLAUSE.get(profile.key, "")
    if clause and bank:
        name, desc, weight = bank[-1]
        if clause not in desc:
            bank[-1] = (name, f"{desc} {clause}", weight)

    if not position_index or not bank or len(bank) < 2:
        # Established single-lesson behaviour: the indicator's own activity
        # phases when genuinely expressed, else the subject profile's phases.
        return bank or profile_phases

    source = profile_phases if position_index % 2 else bank
    if len(source) < 2:
        return bank or profile_phases
    shift = ((position_index + 1) // 2) % len(source)
    return source[shift:] + source[:shift]


#: Words that begin a focus and must NOT be lower-cased into mid-sentence.
_PROPER_NOUN_STARTS = {
    "windows", "start", "nacca", "ghana", "english", "mathematics",
    "computing", "microsoft", "god's", "africa", "technolog",
}


def _objective_focus(focus: str) -> str:
    """A curriculum focus, phrased to follow an objective verb naturally.

    "Fourth-generation computers and the microchip" becomes lower-case so it
    reads mid-sentence; a proper noun (Windows, NaCCA) keeps its capital.
    """
    text = (focus or "").strip()
    if not text:
        return text
    first = text.split(" ", 1)[0].rstrip(":").lower()
    if first in _PROPER_NOUN_STARTS:
        return text
    return text[:1].lower() + text[1:]


def skill_from_source(alloc: AllocatedIndicator) -> bool:
    """True when the teacher's scheme states usable indicator PROSE.

    A code-only cell ("B7.1.1.1.2") is not teachable text, so the scheme is not
    the source of the lesson's focus in that case — the official curriculum
    corpus is. A scheme that does state prose always wins over the corpus.
    """
    text = (getattr(alloc, "indicator_description", "") or "").strip()
    return bool(text) and not _is_code_only(text)


def _exemplar_for(alloc: AllocatedIndicator, subject_name: str):
    """Official NaCCA exemplar evidence for this lesson, or None.

    Resolved by INDICATOR code only. The content-standard code is deliberately
    not used as a fallback: "B7.1.1.1" is the first content standard of Strand
    1 in every subject, and a record describes its own indicator's exemplars —
    attaching it to some other indicator of the same standard would attribute
    one indicator's curriculum evidence to another lesson (PART 33).

    A subject mismatch also returns None: another subject's curriculum
    evidence is never substituted.
    """
    try:
        from .exemplars import lookup_indicator
    except Exception:  # pragma: no cover - corpus is optional infrastructure
        return None
    code = getattr(alloc, "indicator_code", "") or ""
    if not code:
        return None
    return lookup_indicator(code, subject_name)


#: Verbs that can be written as a measurable "Learners can <verb> ..."
#: objective. The corpus stores the verbs the official exemplars actually use;
#: some of them ("discover", "practise", "show") describe the activity rather
#: than an assessable outcome, so the planner prefers the first measurable verb
#: the same exemplar supports.
_MEASURABLE_OBJECTIVE_VERBS = {
    "identify", "describe", "demonstrate", "compare", "classify",
    "explain", "apply", "investigate", "distinguish", "examine",
    "categorise", "categorize", "discuss", "design", "state", "list",
    "model", "represent", "determine", "analyse", "analyze", "evaluate",
    "outline", "use", "create", "perform", "measure", "calculate",
    "interpret", "justify", "name", "recite", "write", "read",
    "pronounce", "match", "arrange", "sort", "construct", "draw",
}


def _objective_verb(exemplar) -> str:
    """The exemplar's most measurable action verb (falling back to its first)."""
    verbs = [str(v).strip().lower() for v in (exemplar.curriculum_action_verbs or [])
             if str(v).strip()]
    for verb in verbs:
        if verb in _MEASURABLE_OBJECTIVE_VERBS:
            return verb
    return verbs[0] if verbs else "explain"


def _exemplar_phases(exemplar, fmt: Dict[str, str]) -> List[Tuple[str, str, float]]:
    """MAIN phases from the official exemplar's own derived activity patterns.

    Patterns are ordered by the corpus: ``[0]`` is the opening (used as the
    starter), ``[1]`` the teacher-led teaching step and ``[2]`` the learners'
    guided task. A record with fewer patterns falls back to the pedagogy bank
    for the missing positions — the lesson is never left with one phase.
    """
    patterns = [p.strip() for p in (exemplar.exemplar_activity_patterns or [])
                if (p or "").strip()]
    names = [
        "Teaching and demonstration",
        "Guided learner task",
        "Application and assessment",
    ]
    weights = [0.40, 0.35, 0.25]
    phases: List[Tuple[str, str, float]] = []
    for i, pattern in enumerate(patterns[1:4]):
        phases.append((
            names[i] if i < len(names) else f"Step {i + 2}",
            _safe_format(pattern, **fmt),
            weights[i] if i < len(weights) else 0.25,
        ))
    return phases


def build_lesson(
    alloc: AllocatedIndicator,
    config: TermConfig,
    scheme_id: str,
    previous_indicator: Optional[str] = None,
    next_indicator: Optional[str] = None,
    position_index: int = 0,
    day_label: str = "",
    previous_day_label: str = "",
    pattern: Optional["LessonPattern"] = None,
    batch_history: Optional["BatchHistory"] = None,
) -> LessonPlan:
    """Compose one deterministic, subject-aware, indicator-specific lesson plan.

    ``position_index``/``day_label``/``previous_day_label`` place the lesson
    inside a class-teacher teaching WEEK (Basic 1-3 weekly plans): position 0
    is the week's first lesson of that subject and keeps the established
    single-lesson output exactly, while later positions open with an explicit
    link to the previous teaching day and compose a different MAIN block (see
    ``_compose_main_phases``) so repeated curriculum focus across days is never
    cloned. The parameters default to the single-lesson behaviour, so every
    existing caller (Basic 4-JHS, KG, Nursery, subject-teacher WAPEF) is
    unchanged.

    ``pattern`` (Layer 3) optionally supplies the teaching SEQUENCE: the MAIN
    phases are then composed from the pattern's step roles rendered through
    the subject's own pedagogy moves, the starter from the pattern's starter
    mode and the plenary from its plenary mode. It defaults to ``None`` — the
    established output is byte-for-byte preserved — and the allocation engine
    passes a selected pattern during batch generation only. The pattern
    supplies the SHAPE of the lesson; the indicator remains the substance.

    ``batch_history`` (Layer 4) records the generated lesson's fingerprint for
    anti-repetition. It never changes this lesson's text; it only lets the
    NEXT selection vary. It is optional and never required for a valid lesson.
    """
    subject_name = (
        config.subject.value if isinstance(config.subject, Subject) else str(config.subject)
    )
    profile: SubjectPedagogy = profile_for_subject(subject_name)
    class_level = (
        config.class_level.value
        if isinstance(config.class_level, ClassLevel) else str(config.class_level)
    )
    # KG and Nursery classes are developmentally early-childhood regardless
    # of the subject label the file was confirmed under: a KG2 "Numeracy" row
    # is taught through play, songs and concrete objects — not the board-worked
    # examples and written class exercises of the Basic-7-9 mathematics
    # profile. The KG1/KG2 source evidence (play-based authentic assessment,
    # observation checklists, songs and role-play in the resource columns)
    # supports the early-childhood profile for every KG subject area. Nursery
    # keeps its OWN profile: the source evidence there is oral instruction,
    # teacher modelling, guided participation and playful practice with the
    # scheme's own resources — a younger cohort than KG, with simpler
    # outcomes. Basic 1+ keeps the subject profile.
    if class_level in ("KG 1", "KG 2"):
        from .pedagogy import SUBJECT_PROFILES
        profile = SUBJECT_PROFILES["early_childhood"]
    elif class_level in ("Nursery", "Nursery 1", "Nursery 2"):
        from .pedagogy import SUBJECT_PROFILES
        profile = SUBJECT_PROFILES["nursery"]

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

    # ── Official NaCCA exemplar evidence (PHASE 1-4) ─────────────────────
    # The teacher's scheme remains the authority for SEQUENCE and for any
    # indicator prose it states. The corpus supplies the PEDAGOGICAL EVIDENCE
    # for this indicator (derived, never a verbatim copy, and only ever present
    # when the official source was actually read for it). When the scheme prints
    # codes only — the real Computing-scheme shape — the corpus is what stops
    # every indicator in the sub-strand sharing one generic focus.
    exemplar = _exemplar_for(alloc, subject_name)
    if exemplar is not None and skill_from_source(alloc):
        # The scheme states this indicator's own wording, and that wording is
        # the authority for what the lesson teaches. A corpus record is keyed
        # by the same CODE but describes the OFFICIAL indicator of that code;
        # schools renumber, so "B7.1.1.1.1 Add whole numbers up to 1000" must
        # never receive the official B7.1.1.1.1 place-value-and-billions
        # activities. With the source's own prose the corpus steps aside
        # entirely and the subject pedagogy composes the lesson.
        exemplar = None
    if exemplar and not skill:
        skill = exemplar.learning_focus
        focus_short = exemplar.learning_focus
    # Nursery-style rows (and KG code-only rows) carry no indicator prose: the
    # source row itself (strand + sub-strand) is the authoritative curriculum
    # focus. The sub-strand names what the lesson actually teaches; the strand
    # alone is never inflated into a fake indicator.
    if not skill and alloc.sub_strand:
        skill = alloc.sub_strand
        focus_short = alloc.sub_strand
    topic = _derive_topic(alloc)
    if exemplar and not skill_from_source(alloc):
        # Code-only source: the corpus focus is more useful than the shared
        # sub-strand as the lesson topic.
        topic = exemplar.learning_focus
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
    exemplar_starter = ""
    if exemplar and (exemplar.exemplar_activity_patterns or []):
        exemplar_starter = (exemplar.exemplar_activity_patterns[0] or "").strip()
    if pattern is not None and pattern.starter_mode in STARTER_MODE_TEMPLATES:
        # Layer 3: the selected pattern opens the lesson with its own concrete
        # teacher + learner action. The indicator stays the subject of every
        # sentence via {focus_short}; the mode only changes HOW it opens, so a
        # batch does not share one opening skeleton.
        starter = _safe_format(STARTER_MODE_TEMPLATES[pattern.starter_mode], **fmt)
        if prev_short:
            starter = f"Build on the previous lesson ('{prev_short}'). " + starter
        if position_index and (prev_short or focus_short):
            link = prev_short or focus_short
            label = previous_day_label or "the previous lesson"
            starter = f"Continue from {label} on '{link}'. " + starter
    elif exemplar_starter:
        # The official exemplar's own derived opening activity: concrete
        # teacher action, learner action and object, replacing the generic
        # prior-knowledge formula.
        starter = _safe_format(exemplar_starter, **fmt)
        if prev_short:
            starter = f"Build on the previous lesson ('{prev_short}'). " + starter
    else:
        starter_line = _STARTER_BANK.get(act_key) or profile.starter_template
        starter = _safe_format(starter_line, **fmt)
        if position_index and (prev_short or focus_short):
            # A class-teacher week (Basic 1-3): the day's starter names the
            # teaching day it continues from, so two days on the same curriculum
            # focus open differently instead of repeating one sentence.
            link = prev_short or focus_short
            label = previous_day_label or "the previous lesson"
            starter = f"Continue from {label} on '{link}'. " + starter
        elif prev_short:
            starter = f"Build on the previous lesson ('{prev_short}'). " + starter
        if misconceptions and "Monitor for general" not in misconceptions:
            starter += f" Watch for: {misconceptions}"
    # ``introduction`` is the lesson-level framing (how this lesson connects to
    # the last one and where it sits in the topic); ``starter_activity`` is the
    # concrete opening activity. Keeping them distinct stops the same sentence
    # being emitted twice into the exported plan.
    if prev_short:
        intro = f"This lesson builds on '{prev_short}' and moves the class on to {skill}."
    elif topic and topic.strip() and topic.strip().lower() != (skill or "").strip().lower():
        intro = f"This lesson focuses on {skill} within {topic}."
    else:
        # The topic IS the focus (a code-only scheme filled from the official
        # exemplar corpus): "within {topic}" would repeat the same words twice.
        intro = f"This lesson focuses on {skill}."
    if position_index:
        # Same curriculum focus on a later teaching day: the framing states the
        # continuation explicitly (never a cloned opening sentence).
        label = previous_day_label or "the previous lesson"
        link = prev_short or focus_short or skill
        intro = (f"This lesson continues the week's work from {label} on "
                 f"'{link}' and develops {skill}.")

    # ── MAIN — phases follow the indicator's activity type ──────────────
    starter_min = max(5, round(duration * 0.15))
    plenary_min = max(5, round(duration * 0.20))
    # An official exemplar record supplies the MAIN block from its own derived
    # activity patterns; otherwise the indicator's activity bank / subject
    # profile composes it (unchanged behaviour for subjects without a record).
    exemplar_phases = _exemplar_phases(exemplar, fmt) if exemplar else []
    # Layer 3: when a teaching pattern was selected, its step sequence composes
    # the MAIN block — rendered through the subject's own pedagogy moves so the
    # same pattern reads differently per subject. Indicator-specific content
    # (verbs, resources, competencies, assessment) is NOT touched; the pattern
    # only supplies the teaching shape.
    if pattern is not None:
        pattern_specs: List[Tuple[str, str, float]] = []
        for step in pattern.steps:
            rendered = _render_pattern_step(step, fmt, profile, act_key)
            if rendered and rendered[1].strip():
                pattern_specs.append(rendered)
        if len(pattern_specs) >= 2:
            # A pattern with fewer than two renderable steps falls back to the
            # established composition rather than producing a thin MAIN block.
            phase_specs = pattern_specs
        else:
            phase_specs = _compose_main_phases(profile, fmt, act_key,
                                               position_index=position_index)
    elif len(exemplar_phases) >= 2:
        # The approved plan's MAIN block spans at least three phases. The
        # exemplar's own derived patterns fill it first — they are specific to
        # THIS indicator — and the subject's activity bank supplies any
        # remaining positions so the subject's own teaching language (worked
        # example, prediction, investigation, model and production) is not
        # lost when a record covers an indicator only briefly.
        for extra in _compose_main_phases(profile, fmt, act_key,
                                          position_index=position_index):
            if len(exemplar_phases) >= 3:
                break
            if extra[1].strip() not in {p[1].strip() for p in exemplar_phases}:
                exemplar_phases.append(extra)
        phase_specs = exemplar_phases
    else:
        phase_specs = _compose_main_phases(profile, fmt, act_key,
                                           position_index=position_index)
    main_total = max(duration - starter_min - plenary_min, len(phase_specs))
    phase_minutes = _distribute(main_total, [p[2] for p in phase_specs])

    # Learner activities come from the SAME activity-type bank as the teacher's,
    # so the learner column is equally specific to the indicator — never the
    # generic "Watch and listen carefully" / "Complete the task" fallbacks.
    learner_bank = _LEARNER_PHASE_BANK.get(act_key) or []

    main_activities: List[TeachingActivity] = []
    learner_activities: List[TeachingActivity] = []
    teacher_activities: List[TeachingActivity] = []
    for idx, ((phase_name, desc, _), minutes) in enumerate(
        zip(phase_specs, phase_minutes)
    ):
        main_activities.append(TeachingActivity(
            phase=phase_name.upper(), description=desc,
            duration_minutes=minutes, resources=[],
        ))
        # Prefer the learner bank's own phase at the same position; fall back
        # to a learner reframing of the teacher phase name only when the bank
        # has no entry for this activity type.
        if idx < len(learner_bank):
            learner_desc = _safe_format(learner_bank[idx][1], **fmt)
        else:
            learner_desc = _learner_task(phase_name, focus_short)
        learner_activities.append(TeachingActivity(
            phase="LEARNER",
            description=learner_desc,
            duration_minutes=minutes, resources=[],
        ))
        teacher_activities.append(TeachingActivity(
            phase="TEACHER",
            description=_teacher_move(phase_name, focus_short),
            duration_minutes=minutes, resources=[],
        ))

    # ── ASSESSMENT — measures THIS indicator's evidence ─────────────────
    if exemplar and exemplar.assessment_patterns:
        # Assessment comes from the official exemplar's own derived evidence
        # check: what the teacher looks and listens for in THIS indicator.
        assessment = " ".join(
            p.strip() for p in exemplar.assessment_patterns if (p or "").strip()
        )
    else:
        assessment_tmpl = _ASSESSMENT_BANK.get(act_key) or profile.assessment_template
        assessment = _safe_format(assessment_tmpl, **fmt)
    if assessment_mode and assessment_mode.lower() not in assessment.lower():
        assessment += f" Assessment mode: {assessment_mode}"
    if not exemplar and not alloc.indicator_description:
        # Indicatorless rows (Nursery week-units): the observation target is
        # the row's own focus, so evaluation stays lesson-specific instead of
        # one generic formula for every week — without inventing any test or
        # curriculum code the source does not have.
        assessment += (
            f" Evidence: each child shows or names one example of "
            f"{(alloc.sub_strand or alloc.strand or 'the lesson focus').strip()}."
        )

    # ── PLENARY — consolidates THIS indicator ───────────────────────────
    if pattern is not None and pattern.plenary_mode in PLENARY_MODE_TEMPLATES:
        # Layer 3: the pattern's closing moment — always a consolidation that
        # produces evidence of understanding, never a bare "review the lesson".
        conclusion = _safe_format(
            PLENARY_MODE_TEMPLATES[pattern.plenary_mode], **fmt)
        if next_short:
            conclusion += f" Preview the next lesson ('{next_short}')."
    else:
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

    # ── Assignments (PART 15) — class work and follow-up home work ──────
    # Both follow the indicator's OWN activity type: a classification lesson
    # sets a sorting task, an investigation sets an observation follow-up.
    # The teacher edits both in the workspace; the legacy single ``homework``
    # column mirrors the home assignment so templates that declare only a
    # Homework row still render the follow-up. Never a written homework
    # question forced onto every indicator.
    if exemplar and exemplar.class_assignment_pattern.strip():
        class_assignment = _safe_format(exemplar.class_assignment_pattern, **fmt)
    else:
        class_assignment = _safe_format(
            _CLASS_ASSIGNMENT_BANK.get(act_key)
            or _CLASS_ASSIGNMENT_BANK["demonstration"], **fmt)
    if exemplar and exemplar.home_assignment_pattern.strip():
        home_assignment = _safe_format(exemplar.home_assignment_pattern, **fmt)
    else:
        home_assignment = _safe_format(
            _HOME_ASSIGNMENT_BANK.get(act_key)
            or _HOME_ASSIGNMENT_BANK["demonstration"], **fmt)

    # ── Resources — THIS lesson's scheme TLRs first, then activity extras ──
    # SOURCE TLRs: from the scheme for this subject + source week + indicator.
    # NEVER from another subject, another week, a static profile, or AI.
    # CANONICAL RESOURCES (PART 6/7): normalize_text_items repairs legacy
    # rows (one comma-joined / serialized string) into individual entries and
    # guards against any accidental stringification reaching a lesson.
    source_tlrs: List[str] = []
    for r in normalize_text_items(list(getattr(alloc, "source_resources", []) or [])):
        r = (r or "").strip()
        if r and r.lower() not in [x.lower() for x in source_tlrs]:
            source_tlrs.append(r)

    # OTHER TLRs: teacher additions for THIS lesson only (PART I).
    # DEFAULT: empty. The old global config seed is NOT copied here — a batch
    # seed value must never silently become per-lesson "teacher-added" data.
    # The teacher adds Other TLRs per lesson in review; AI suggestions never
    # land here either (they may only enrich the display union).
    other_tlrs: List[str] = []

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
    # Official curriculum material patterns for THIS indicator (e.g. "picture
    # cards showing keyboard, mouse, touchscreen, barcode reader, scanner").
    if exemplar:
        for r in (exemplar.suitable_resource_patterns or []):
            r = (r or "").strip()
            if r and r.lower() not in [x.lower() for x in resources]:
                resources.append(r)

    # ── Keywords / vocabulary — PER-LESSON, curriculum-derived (PART G) ──
    # Priority: exact lesson indicator / learning focus first, then sub-strand,
    # then content standard, then subject-level activity context. Two lessons
    # under the same scheme therefore do NOT receive one identical generic
    # list merely because they share a subject: each list is derived from THIS
    # lesson's own indicator/row text. AI may refine these in review; the
    # teacher's edits always win once saved.
    keywords: List[str] = []
    kw_sources: List[str] = []
    # 1. Scheme resources are the PRIMARY keyword seed (PART 14): the teacher's
    #    own scheme names the concrete materials for THIS lesson ("light pen",
    #    "touchscreen", "mouse", "keyboard", "personal computer"), which are far
    #    more lesson-specific than the shared sub-strand. Normalized and deduped.
    for r in normalize_text_items(list(getattr(alloc, "source_resources", []) or [])):
        r = (r or "").strip()
        if r and r.lower() not in [x.lower() for x in keywords]:
            keywords.append(r)
    # 2. Official exemplar focus terms for THIS indicator (concrete curriculum
    #    vocabulary such as "microchip" or "barcode reader") before the
    #    generic sub-strand can contribute anything.
    if exemplar:
        kw_sources.extend(exemplar.focus_terms or [])
    # 3. Exact lesson indicator / learning focus.
    kw_sources.extend(_content_terms(alloc.indicator_description, limit=5))
    # 3. Sub-strand (the lesson's own curriculum focus when no indicator prose).
    #    Limited to 2 so the shared sub-strand cannot dominate the list.
    kw_sources.extend(_content_terms(alloc.sub_strand or "", limit=2))
    # 4. Content standard.
    kw_sources.extend(_content_terms(alloc.content_standard_description or "", limit=2))
    # 5. Lesson-specific activity context from the interpreter.
    if act_key and interp is not None:
        kw_sources.extend(getattr(interp, "activity_keywords", []) or [])
    # Teacher-supplied PER-LESSON terms always survive (never a batch seed).
    kw_sources.extend((getattr(config, "keywords", []) or []))
    for k in kw_sources:
        k = (k or "").strip()
        kl = k.lower()
        if not k or len(kl) < 3 or kl in _KEYWORD_NOISE:
            continue
        # A single generic Bloom verb is not lesson vocabulary.
        if " " not in kl and kl in _BLOOM_ACTION_WORDS:
            continue
        if kl not in [x.lower() for x in keywords]:
            keywords.append(k)

    # ── Core competencies — PER-LESSON, activity-derived (PART H) ───────
    # AI-suggested + teacher-editable. ONLY the competencies meaningful for
    # THIS lesson's activity type are selected — never the whole taxonomy for
    # every lesson. Teacher multi-select is authoritative once set on the
    # lesson review object; the generator never re-forces a removed value.
    competencies: List[str] = []
    comp_sources = list(getattr(config, "core_competencies", []) or [])
    if exemplar and exemplar.core_competencies:
        # The competencies the official curriculum attaches to THIS indicator
        # (PART 1) rather than the activity-type default.
        comp_sources.extend(exemplar.core_competencies)
    else:
        comp_sources.extend(_COMPETENCIES_BY_ACTIVITY.get(act_key or "demonstration", []))
    for c in comp_sources:
        c = (c or "").strip()
        if c and c.lower() not in [x.lower() for x in competencies]:
            competencies.append(c)

    # ── References — TEACHER-ENTERED only (PART L/M) ────────────────────
    # DEFAULT: empty. The builder never invents curriculum/handbook references:
    # the review UI presents 3 empty structured slots and the teacher fills
    # what applies to THIS lesson (different lessons may cite different pages).
    # Teacher-supplied flat seed strings still become structured Other entries
    # (pages stay blank unless explicitly supplied), but no fabricated defaults.
    references: List[str] = []
    structured_refs = []
    from ..models import ReferenceEntry
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
                else (
                    # Nursery: the source (sub-strand topics such as "Sorting
                    # and matching", "Colouring, Tracing and Alphabets") asks
                    # children to DO and SAY — a demonstrable "show" outcome,
                    # not Basic-style measurable analysis and not the KG
                    # role-play phrasing.
                    f"Learners can show and talk about "
                    f"{(alloc.sub_strand or alloc.strand or 'the lesson focus').strip()}"
                    if class_level in ("Nursery", "Nursery 1", "Nursery 2")
                    else f"Learners can explore and talk about {(alloc.sub_strand or alloc.strand or 'the lesson focus').strip()}"
                )
            )
        ),
        indicator_code=alloc.indicator_code or None,
    )]

    # PHASE 6: when the scheme prints codes only, the objective comes from the
    # official exemplar's OWN action verb and focus — measurable, lesson
    # specific, and aligned with the assessment and assignments above. A scheme
    # that states its own indicator prose is never overridden (source
    # authority).
    if exemplar and not skill_from_source(alloc) and objectives:
        verb0 = _objective_verb(exemplar)
        objectives[0] = LearningObjective(
            description=f"Learners can {verb0} {_objective_focus(exemplar.learning_focus)}",
            indicator_code=alloc.indicator_code or None,
        )

    previous_knowledge = (
        f"Previous lesson: {prev_short}" if prev_short
        else "Learners' everyday experience related to this activity."
    )

    essential_question = _safe_format(
        _ESSENTIAL_BANK.get(act_key) or profile.essential_question, **fmt
    )

    lp = LessonPlan(
        scheme_of_work_id=scheme_id,
        term_config_id=config.id,
        week_number=alloc.week_number,
        # INTERNAL diagnostic only (never persisted, never shown): the teaching
        # pattern this lesson was sequenced from, so the batch benchmark can
        # verify selection genuinely varied. Empty when no pattern was used.
        pattern_id=(pattern.id if pattern is not None else ""),
        week_ending=alloc.week_ending,
        week_ending_derived=bool(getattr(alloc, "week_ending_derived", False)),
        teaching_week=alloc.teaching_week or alloc.week_number,
        carry_forward=bool(alloc.carry_forward),
        lesson_sequence=0,  # assigned by the caller (curriculum order)
        # The lesson date is the allocation's own teaching date; failing that
        # the source week's ending date; only then the term window. A TermConfig
        # whose term dates the teacher left unset is resolved from the scheme by
        # the routers, but the builder must still never emit a null lesson date
        # (real-use remediation, Defect 6/7).
        lesson_date=(
            alloc.lesson_date
            or alloc.week_ending
            or config.term_start_date
            or date.today()
        ),
        lesson_number=alloc.period_index,
        period="",  # caller sets the period label
        class_level=config.class_level,
        subject=config.subject,
        class_size=config.class_size,
        duration_minutes=duration,
        school_name=config.school_name,
        teacher_name=config.teacher_name,
        # Persisted per lesson so an export re-renders in the SAME template
        # the teacher approved, even from a later session (template fidelity).
        template_id=getattr(config, "template_id", None),
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
        class_assignment=class_assignment,
        home_assignment=home_assignment,
        homework=home_assignment,
        differentiation=differentiation,
        conclusion=conclusion,
        structured_references=structured_refs,
        references=references,
        status=LessonStatus.GENERATED,
        ai_generated=False,
    )

    # ── Layer 4: record this lesson's fingerprint for anti-repetition ────
    # The history is optional and NEVER changes this lesson's text; it only
    # lets the NEXT lesson's pattern selection vary. Recording happens after
    # the lesson is fully composed so every field is final.
    if batch_history is not None and pattern is not None:
        try:
            from .variation import fingerprint_lesson
            batch_history.record(fingerprint_lesson(
                lp, pattern_id=pattern.id,
                starter_mode=pattern.starter_mode,
                plenary_mode=pattern.plenary_mode,
            ))
        except Exception:
            # History recording must never break a deterministic generation.
            pass

    return lp


def _learner_task(phase_name: str, skill: str) -> str:
    name = (phase_name or "").lower()
    if "play" in name or "game" in name or "song" in name or "rhyme" in name:
        # Early-years playful practice (Nursery/KG "Playful practice"): the
        # child joins in — doing, saying, sorting, singing — with the group.
        return f"Join in the play or song about {skill} and try it yourself."
    if "demonstrat" in name or "model" in name or "explanation" in name or "teaching" in name or "predict" in name or "stimulus" in name or "inspiration" in name or "present" in name or "vocabulary" in name:
        return f"Watch and listen carefully, then describe each step of {skill} in your own words."
    if "independent" in name or "application" in name or "challenge" in name or "creation" in name or "try" in name or "comprehension" in name or "findings" in name or "sharing" in name or "accuracy" in name or "practice" in name:
        # "practice" belongs with independent attempts: a guided step and a
        # practice step must not emit the same learner sentence.
        return f"Complete the task for {skill} on your own and check your work before you finish."
    if "guided" in name or "observation" in name or "discussion" in name or "recording" in name or "investigation" in name or "analysis" in name or "guided writing" in name or "guided reading" in name or "comparison" in name or "first item" in name or "second item" in name or "experience" in name or "participation" in name:
        return f"Work with your partner/group to carry out the task for {skill} and record what you find."
    if "critique" in name or "reflection" in name or "revision" in name or "improve" in name:
        return f"Look at your work on {skill}, decide what went well and what to improve."
    return f"Take an active part in the activity for {skill}."


def _teacher_move(phase_name: str, skill: str) -> str:
    name = (phase_name or "").lower()
    if "play" in name or "game" in name or "song" in name or "rhyme" in name:
        # Early-years playful practice (Nursery/KG): the teacher watches,
        # encourages and names what each child is doing — no written marking.
        return f"Watch the children as they play at {skill}, encourage them by name and praise their attempts."
    if "demonstrat" in name or "model" in name or "explanation" in name or "teaching" in name or "predict" in name or "stimulus" in name or "inspiration" in name:
        return f"Model {skill} slowly, think aloud, and check that all learners can see and hear."
    if "independent" in name or "application" in name or "challenge" in name or "creation" in name or "try" in name or "comprehension" in name or "findings" in name or "sharing" in name or "accuracy" in name or "practice" in name:
        return f"Circulate, give brief individual feedback, and note learners who need re-teaching of {skill}."
    if "guided" in name or "observation" in name or "discussion" in name or "recording" in name or "investigation" in name or "analysis" in name or "guided writing" in name or "guided reading" in name or "participation" in name:
        # "participation" is a guided step (the teacher helps each child by
        # name), not an independent-practice step.
        return f"Move around the room, observe each group, and correct misconceptions about {skill} on the spot."
    if "critique" in name or "reflection" in name or "revision" in name:
        return f"Lead a short, kind critique and highlight good examples relating to {skill}."
    return f"Facilitate the activity and keep every learner focused on {skill}."

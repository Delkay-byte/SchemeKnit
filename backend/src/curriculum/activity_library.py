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
    #: Interpreter activity types this structure suits (the exact
    #: ``ACTIVITY_KEYWORDS`` keys: problem_solving, classification, …).
    #: ``select_activity`` weighs the interpreter's type hint against this
    #: list — without it the hint never matched any id and was dead weight.
    activity_types: Tuple[str, ...] = ()
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
        activity_types=("classification", "comparison"),
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
        activity_types=("problem_solving",),
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
        activity_types=("investigation", "observation"),
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
        activity_types=("demonstration", "practical"),
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
        activity_types=("reading", "writing", "discussion"),
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
        activity_types=("creation", "practical"),
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
        activity_types=("discussion", "analysis"),
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
        activity_types=("observation",),
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
        activity_types=("practical", "discussion"),
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
    # ── Priority 2.1 §C: structures for the verbs and subjects the original
    # eight entries did not cover (retelling, singing, labelling, locating,
    # arguing, assessing, sequencing, troubleshooting, playing, reflecting,
    # presenting, critiquing, early-years trace/colour/count). Ties always
    # favour the earlier entries, so nothing the original library already
    # handled well moves. ────────────────────────────────────────────────
    ActivityPattern(
        id="guided_reading_comprehension",
        title="Guided reading then retell",
        action_verbs=("retell",),
        subjects=("english",),
        activity_types=("reading", "discussion"),
        cognitive_action="understand",
        teacher_action=("Read the passage on {focus} aloud once, pausing at "
                        "the key events or ideas, then reread the important "
                        "sentences with the class."),
        learner_action=("Read along quietly, mark two key sentences, then "
                        "retell what the text says about {focus} in their own "
                        "words to a partner."),
        materials=("reader or story text", "chalkboard", "exercise books"),
        evidence=("Each learner retells the passage's main idea about "
                  "{focus} with at least the two key events or facts intact."),
        assessment=("Comprehension check: learners write two sentences "
                    "retelling {focus} from the text. Success = both "
                    "sentences factually match the passage."),
        support=("Provide five comprehension questions with a word bank "
                 "from the passage."),
        challenge=("Retell the passage from a different character's point "
                   "of view and justify the change."),
        stages=("first", "repeat"),
        ghana_context=("Choose a passage from Ghanaian folktales, local "
                       "news or community life so comprehension starts from "
                       "familiar content.",),
        adaptation="The text can be dictated or written on the board when "
                   "there are not enough readers.",
    ),
    ActivityPattern(
        id="guided_writing_composition",
        title="Model then guided writing",
        action_verbs=("draft", "publish", "compose", "punctuate", "spell"),
        subjects=("english",),
        activity_types=("writing",),
        cognitive_action="create",
        teacher_action=("Model one short piece for {focus} on the board, "
                        "thinking through planning, sentences and punctuation "
                        "aloud as it is written."),
        learner_action=("Plan, draft and write their own short piece on "
                        "{focus}, then reread it to correct one punctuation "
                        "or spelling error before submitting."),
        materials=("exercise books", "chalkboard", "writing materials"),
        evidence=("Every learner submits a complete written piece on "
                  "{focus} of the required length with correct sentence "
                  "boundaries."),
        assessment=("Mark the short writing against three criteria: content "
                    "about {focus}, sentence structure and punctuation. "
                    "Success = all three met."),
        support=("Provide a sentence frame, a model paragraph and the key "
                 "vocabulary for {focus}."),
        challenge=("Improve the piece after peer feedback and explain which "
                   "change made it clearer."),
        stages=("first", "repeat"),
        ghana_context=("Set the writing in learners' own names, homes or "
                       "local events so the content is real to them.",),
        adaptation="Model on the board; no printed writing sheets needed.",
    ),
    ActivityPattern(
        id="listen_and_respond",
        title="Listen then respond",
        action_verbs=("listen", "respond"),
        subjects=("english", "early_childhood"),
        activity_types=("reading", "discussion"),
        cognitive_action="understand",
        teacher_action=("Read or say the text for {focus} twice — once for "
                        "the overall meaning, once stopping after each key "
                        "line for a quick response."),
        learner_action=("Listen for the key words, then answer two oral "
                        "questions and repeat the correct line about "
                        "{focus} together."),
        materials=("reader or audio text", "chalkboard"),
        evidence=("Learners answer both oral questions about {focus} "
                  "correctly and repeat the key line intelligibly."),
        assessment=("Oral check: ask two questions on {focus} after the "
                    "second listening; each learner answers unprompted. "
                    "Success = both answers correct."),
        support=("Repeat more slowly and give two to three choices for "
                 "each answer."),
        challenge=("Predict what happens next in the text and justify the "
                   "prediction from what was heard."),
        stages=("first", "repeat"),
        ghana_context=("Use a familiar Ghanaian song, market exchange or "
                       "family conversation as the listening text.",),
        adaptation="The teacher's voice is the audio equipment; nothing is played.",
    ),
    ActivityPattern(
        id="sing_and_perform",
        title="Sing, then perform with meaning",
        action_verbs=("sing", "dance", "chant"),
        subjects=("creative_arts", "english"),
        activity_types=("creation", "practical"),
        cognitive_action="apply",
        teacher_action=("Sing or chant the piece for {focus} once, marking "
                        "the beat and the words, then point out the one "
                        "phrase learners must get right."),
        learner_action=("Join in on the first singing, then perform it in "
                        "small groups with the correct words, beat and "
                        "expression, and name what the song says about "
                        "{focus}."),
        materials=("chalkboard for the words", "open space",
                   "simple percussion if available"),
        evidence=("Groups perform the song or chant about {focus} with the "
                  "correct words and beat, and one learner states its "
                  "message."),
        assessment=("Perform each group once against three criteria: correct "
                    "words, steady beat, clear expression. Success = all "
                    "three, plus one stated message about {focus}."),
        support=("Provide the words on the board and lead line by line "
                 "before group performance."),
        challenge=("Add a verse or movement of their own that carries the "
                   "same message about {focus}."),
        stages=("first", "repeat"),
        ghana_context=("Draw the song from Ghanaian nursery rhymes, "
                       "traditional or class songs the learners already "
                       "know.",),
        adaptation="No instruments needed; clapping carries the beat.",
    ),
    ActivityPattern(
        id="trace_colour_make",
        title="Trace, colour and make",
        action_verbs=("trace", "colour", "color", "paste", "cut", "fold"),
        subjects=("early_childhood", "nursery", "creative_arts"),
        activity_types=("practical", "creation"),
        cognitive_action="apply",
        teacher_action=("Model each step of the task on {focus} slowly: "
                        "trace the outline, colour within the lines, then "
                        "cut or fold where shown."),
        learner_action=("Carry out each step themselves on their own sheet, "
                        "check the result against the model, and show the "
                        "finished work to a partner."),
        materials=("paper or exercise books", "crayons or pencils",
                   "scissors", "glue"),
        evidence=("Each learner's finished work follows the model's shape "
                  "and colour pattern for {focus}, with no missing step."),
        assessment=("Observe each learner's finished piece against a short "
                    "checklist: traced, coloured, cut/folded correctly. "
                    "Success = all items done."),
        support=("Give a pre-traced outline to start from."),
        challenge=("Draw the same shape from memory without a model."),
        stages=("first", "repeat"),
        ghana_context=("Use local patterns — kente strips, adinkra shapes, "
                       "household objects — as the things to trace and "
                       "colour.",),
        adaptation="Templates can be drawn on the board at the same size.",
    ),
    ActivityPattern(
        id="count_and_practise",
        title="Count with materials, then record",
        action_verbs=("count", "skip"),
        subjects=("early_childhood", "nursery", "mathematics"),
        activity_types=("problem_solving", "practical"),
        cognitive_action="apply",
        teacher_action=("Count aloud with the class using real objects or "
                        "number cards for {focus}, showing how the count is "
                        "recorded."),
        learner_action=("Count the objects themselves in pairs, write the "
                        "total, then count the next set without help and "
                        "check by recounting."),
        materials=("counting materials or number cards", "chalkboard",
                   "exercise books"),
        evidence=("Learners record the correct totals for two counts of "
                  "{focus} and recount to confirm the second."),
        assessment=("Quick check: learners count two fresh sets for "
                    "{focus} and write each total. Success = both totals "
                    "correct."),
        support=("Provide fewer objects at first and count together before "
                 "independent counting."),
        challenge=("Count the same set in groups of two and explain why the "
                   "total does not change."),
        stages=("first", "repeat"),
        ghana_context=("Count real classroom and compound objects — sticks, "
                       "seeds, bottle caps — not pictures of them.",),
        adaptation="Any countable local objects replace purchased counters.",
    ),
    ActivityPattern(
        id="label_annotate_diagram",
        title="Label and annotate a diagram",
        action_verbs=("label", "annotate", "sketch"),
        subjects=("science", "ict"),
        activity_types=("practical",),
        cognitive_action="remember",
        teacher_action=("Draw or display the diagram for {focus} and model "
                        "how to place two labels with a straight leader line "
                        "and a short note."),
        learner_action=("Sketch or trace the diagram of {focus}, add the "
                        "required labels and one annotation explaining what "
                        "each part does."),
        materials=("chart or diagram", "chalkboard", "exercise books",
                   "rulers"),
        evidence=("The learner's diagram carries all required labels for "
                  "{focus} in the correct positions plus one accurate "
                  "annotation."),
        assessment=("Label check: given the same diagram unlabelled, "
                    "learners place at least 4 of 5 labels correctly. "
                    "Success = 4 of 5 plus one correct note."),
        support=("Provide a partially labelled diagram with a label word "
                 "bank."),
        challenge=("Draw the diagram from memory and annotate one part the "
                   "lesson did not label."),
        stages=("first", "repeat"),
        adaptation="Draw one large diagram on the board for the whole class.",
    ),
    ActivityPattern(
        id="map_and_locate",
        title="Read and locate on a map",
        action_verbs=("locate", "plot"),
        subjects=("social_studies",),
        activity_types=("observation", "practical"),
        cognitive_action="apply",
        teacher_action=("Model how to use the map's key and directions to "
                        "locate one place for {focus} on the class map."),
        learner_action=("Use the map to locate the required places for "
                        "{focus}, mark them on their own outline map, and "
                        "state one direction between two of them."),
        materials=("map or outline map", "chalkboard", "exercise books",
                   "rulers"),
        evidence=("Learners mark at least the required places for "
                  "{focus} correctly and state one correct direction."),
        assessment=("Map check: learners locate three unnamed places for "
                    "{focus} on a fresh outline map. Success = all three "
                    "correct."),
        support=("Give a numbered key and a partially completed map."),
        challenge=("Trace and describe a route between two places of their "
                   "own choosing."),
        stages=("first", "repeat"),
        ghana_context=("Start from the learners' own region, district and "
                       "town before locating national places.",),
        adaptation="One shared map plus outline maps drawn on the board work.",
    ),
    ActivityPattern(
        id="debate_and_argue",
        title="State a position and argue it",
        action_verbs=("argue", "defend", "recommend", "persuade"),
        subjects=("social_studies", "rme"),
        activity_types=("discussion",),
        cognitive_action="evaluate",
        teacher_action=("Put the two sides of the issue in {focus} on the "
                        "board and model one claim supported by one piece "
                        "of evidence."),
        learner_action=("Take a side in pairs, give two reasons with one "
                        "example each, then respond to one point from the "
                        "other side."),
        materials=("chalkboard", "source extract or chart",
                   "exercise books"),
        evidence=("Each side states a clear position on {focus} supported "
                  "by two reasons and answers one opposing point."),
        assessment=("Assess each pair's argument on {focus} for: clear "
                    "position, two supported reasons, one response to the "
                    "other side. Success = all three present."),
        support=("Provide two prepared reasons and an example to choose "
                 "from."),
        challenge=("Concede one valid point from the opposition and revise "
                   "their position on {focus} accordingly."),
        stages=("first", "repeat"),
        ghana_context=("Frame the issue in a Ghanaian community or national "
                       "decision learners know.",),
        adaptation="Runs as a seated verbal debate with no materials.",
    ),
    ActivityPattern(
        id="assess_and_review",
        title="Assess work against criteria",
        action_verbs=("assess", "review", "judge"),
        activity_types=("reflection", "analysis"),
        cognitive_action="evaluate",
        teacher_action=("Show one worked example of {focus} and score it "
                        "aloud against the agreed criteria so learners see "
                        "how the judgement is made."),
        learner_action=("Score two pieces of work on {focus} against the "
                        "criteria, record the score with one reason, then "
                        "correct one error they found."),
        materials=("sample work or exercise books", "chalkboard",
                   "criteria list"),
        evidence=("Learners' scores for the samples match the criteria and "
                  "each recorded score carries one accurate reason."),
        assessment=("Moderation check: learners rescore a fresh sample of "
                    "work on {focus}; success = score within one point of "
                    "the teacher's with a valid reason."),
        support=("Give a scored exemplar and a tick-box criteria sheet."),
        challenge=("Improve one sample to meet a higher criterion and "
                   "explain what changed."),
        stages=("first", "repeat"),
        ghana_context=("Use samples of work from the learners' own class, "
                       "never anonymous outside material.",),
        adaptation="Samples can be written on the board for everyone to score.",
    ),
    ActivityPattern(
        id="research_and_report",
        title="Research then report findings",
        action_verbs=("research", "report"),
        subjects=("social_studies",),
        activity_types=("investigation", "discussion"),
        cognitive_action="analyse",
        teacher_action=("Model how to gather two facts about {focus} from "
                        "the available sources and record them in note form."),
        learner_action=("Gather facts on {focus} from the textbook, chart or "
                        "a short approved source, note them, then report two "
                        "findings to the class with the source named."),
        materials=("textbook or source extract", "chalkboard",
                   "exercise books"),
        evidence=("Groups record at least two accurate facts about "
                  "{focus} and report them with their source."),
        assessment=("Report check: each group presents two findings on "
                    "{focus} with sources; success = both facts accurate "
                    "and both sources named."),
        support=("Provide pre-opened pages and three guiding questions."),
        challenge=("Find one conflicting source and explain how they would "
                   "decide which to trust."),
        stages=("first", "repeat"),
        ghana_context=("Where sources are scarce, gather facts from "
                       "community members or local observation and name "
                       "them as sources.",),
        adaptation="One shared textbook can serve the whole class in turns.",
    ),
    ActivityPattern(
        id="sequence_the_steps",
        title="Put the steps in order",
        action_verbs=("sequence", "order"),
        subjects=("ict", "mathematics"),
        activity_types=("practical", "problem_solving"),
        cognitive_action="apply",
        teacher_action=("Scramble the steps of {focus} on the board and "
                        "model re-ordering two of them with a reason."),
        learner_action=("Arrange the full set of steps for {focus} in the "
                        "correct order, number them, and explain why one "
                        "particular step cannot move."),
        materials=("step cards or slips", "chalkboard", "exercise books"),
        evidence=("The learner's sequence matches the correct order for "
                  "{focus} and the stated reason for the fixed step is "
                  "valid."),
        assessment=("Sequencing check: learners order a fresh set of steps "
                    "for {focus}; success = full correct order plus one "
                    "valid reason."),
        support=("Provide step cards with two anchor steps already placed."),
        challenge=("Write the instructions for a classmate so they could "
                   "perform {focus} without help."),
        stages=("first", "repeat"),
        adaptation="Steps can be written as numbered lines on the board.",
    ),
    ActivityPattern(
        id="troubleshoot_and_fix",
        title="Find the fault, fix it",
        action_verbs=("troubleshoot", "format", "save", "print", "browse",
                      "insert", "drag", "debug"),
        subjects=("ict",),
        activity_types=("problem_solving", "practical"),
        cognitive_action="analyse",
        teacher_action=("Present one worked fault in {focus} and think aloud "
                        "through the checks: what should happen, what "
                        "actually happens, what to try first."),
        learner_action=("Work through the checks on their own or the shared "
                        "device, identify the fault in {focus}, fix it, and "
                        "state which check found it."),
        materials=("the shared device or an unplugged model", "chalkboard",
                   "fault checklist"),
        evidence=("The learner identifies the correct fault and restores "
                  "{focus} to working order, naming the check that found it."),
        assessment=("Fault drill: introduce one fault in {focus}; each "
                    "learner (or pair) diagnoses and fixes it. Success = "
                    "correct diagnosis plus working result."),
        support=("Provide a numbered fault-check list and one guided "
                 "example first."),
        challenge=("Given two symptoms, identify which single fault could "
                   "cause both and justify the choice."),
        stages=("first", "repeat"),
        adaptation=("When devices are scarce, run the same diagnostic "
                    "reasoning on a printed or drawn fault scenario.",),
    ),
    ActivityPattern(
        id="game_and_drill",
        title="Game or drill then a quick check",
        action_verbs=("play", "skip", "clap"),
        subjects=("phe", "early_childhood"),
        activity_types=("practical", "observation"),
        cognitive_action="apply",
        teacher_action=("Set up the game or drill for {focus} with clear "
                        "rules, model one round, and state what learners "
                        "should notice or improve."),
        learner_action=("Play or drill the skill in their group for the "
                        "set time, note their own result, then repeat once "
                        "to beat it."),
        materials=("open space", "ball or simple equipment",
                   "chalkboard or markers for scoring"),
        evidence=("Every learner completes the rounds and records a result "
                  "that improves or matches the first attempt at {focus}."),
        assessment=("Observe each learner against three rules-safety-skill "
                    "criteria and record their best attempt at {focus}. "
                    "Success = completed safely with a recorded result."),
        support=("Start with a slower round and a partner to copy."),
        challenge=("Invent one rule variation that makes the game harder "
                   "and explain why it trains {focus} better."),
        stages=("first", "repeat"),
        ghana_context=("Use local playground games and everyday physical "
                       "tasks the children already play at home.",),
        adaptation="Needs only the school compound; no purchased equipment.",
    ),
    ActivityPattern(
        id="reflect_and_discuss",
        title="Reflect then discuss",
        action_verbs=("reflect", "relate"),
        subjects=("rme", "phe", "social_studies"),
        activity_types=("reflection", "discussion"),
        cognitive_action="evaluate",
        teacher_action=("Ask one opening question that links {focus} to the "
                        "learners' own experience, then note three responses "
                        "on the board without judging them."),
        learner_action=("Think silently, then discuss in pairs what "
                        "{focus} means for their own family or community "
                        "and share one agreed point with the class."),
        materials=("chalkboard", "exercise books"),
        evidence=("Pairs share one point about {focus} that is grounded in "
                  "their own experience and stated clearly."),
        assessment=("Written reflection: each learner states one way they "
                    "will apply {focus} this week, with a reason. Success "
                    " = specific action plus reason."),
        support=("Provide two sentence starters: 'In my family…' and "
                 "'This matters because…'."),
        challenge=("Relate {focus} to a situation where following it is "
                   "difficult, and propose how to handle it."),
        stages=("first", "repeat"),
        ghana_context=("Ground every reflection in the learners' own homes, "
                       "streets and community situations.",),
        adaptation="Discussion needs no materials at all.",
    ),
    ActivityPattern(
        id="present_and_share",
        title="Present then take questions",
        action_verbs=("present", "share", "exhibit"),
        subjects=("creative_arts", "career_technology"),
        activity_types=("discussion", "creation"),
        cognitive_action="apply",
        teacher_action=("Model a two-minute presentation of a finished "
                        "piece on {focus}: show it, name two choices, take "
                        "one question."),
        learner_action=("Present their own work on {focus} to the class or "
                        "group in the modelled structure and answer one "
                        "question about a design or process choice."),
        materials=("the finished work or product", "chalkboard"),
        evidence=("Each group presents with a visible product, names two "
                  "choices about {focus}, and answers one question."),
        assessment=("Presentation rubric: product shown, two reasons "
                    "given, one question answered. Success = all three."),
        support=("Provide a three-line presentation frame to read from."),
        challenge=("Exhibit the work with a short written caption that "
                   "invites a specific question from viewers."),
        stages=("first", "repeat"),
        ghana_context=("Present to another group or the class as if "
                       "exhibiting at a school or community show.",),
        adaptation="No display equipment needed; the product is held up.",
    ),
    ActivityPattern(
        id="critique_and_improve",
        title="Critique then improve",
        action_verbs=("critique", "improve", "revise"),
        subjects=("creative_arts", "career_technology"),
        activity_types=("reflection", "creation"),
        cognitive_action="evaluate",
        teacher_action=("Show two pieces on {focus} — one strong, one "
                        "developing — and model naming one strength and one "
                        "specific improvement against the criteria."),
        learner_action=("Critique their own and one peer's work on {focus} "
                        "against two criteria, then make one agreed "
                        "improvement to their own piece."),
        materials=("the works in progress", "criteria list",
                   "exercise books"),
        evidence=("The revised piece visibly changes one named criterion "
                  "for {focus}, and the learner can state what improved."),
        assessment=("Before-and-after check: learners show the improved "
                    "piece and name the criterion it now meets. Success = "
                    "visible change plus accurate statement."),
        support=("Give a criteria checklist with one annotated example."),
        challenge=("Set their own quality criterion for {focus} and meet "
                   "it without teacher prompting."),
        stages=("first", "repeat"),
        ghana_context=("Critique examples drawn from local craft standards — "
                       "neatness of a kente pattern, balance of a pot — "
                       "beside their own work.",),
        adaptation="Peer critique runs verbally with the pieces in hand.",
    ),
    ActivityPattern(
        id="observe_and_describe",
        title="Observe then describe from evidence",
        action_verbs=("observe", "record", "note"),
        subjects=("phe", "science"),
        activity_types=("observation",),
        cognitive_action="analyse",
        teacher_action=("Demonstrate or arrange the event for {focus} once "
                        "and name the two features learners must watch for."),
        learner_action=("Watch the event or demonstration of {focus} twice, "
                        "write down what they actually see for each feature, "
                        "then describe the pattern to a partner."),
        materials=("the real event, apparatus or movement", "chalkboard",
                   "recording sheet or exercise books"),
        evidence=("Learners' written observations record both required "
                  "features of {focus} accurately, without invented detail."),
        assessment=("Observation check: learners describe {focus} from "
                    "their own recorded notes. Success = both features "
                    "present and accurate."),
        support=("Provide a partly filled observation table with sentence "
                 "starters."),
        challenge=("Note one feature the teacher did not name and explain "
                   "its significance for {focus}."),
        stages=("first", "repeat"),
        ghana_context=("Observe a real local phenomenon — weather, plants, "
                       "a playground movement — not an illustration of it.",),
        adaptation="A single shared observation works when materials are few.",
    ),
    ActivityPattern(
        id="summarise_and_restate",
        title="Summarise and restate",
        action_verbs=("summarise", "summarize", "restate"),
        subjects=("english", "social_studies"),
        activity_types=("reading", "writing"),
        cognitive_action="understand",
        teacher_action=("Model a one-sentence summary of {focus} from the "
                        "board notes, showing what was left out and why."),
        learner_action=("Write a one-sentence summary of {focus} in their "
                        "own words, compare it with a partner's, and merge "
                        "the two into the clearest version."),
        materials=("board notes or source text", "exercise books"),
        evidence=("Each learner's summary of {focus} is one sentence, in "
                  "their own words, carrying the central idea."),
        assessment=("Summary check: learners summarise {focus} in one "
                    "sentence; success = central idea present, no copied "
                    "full sentence from the source."),
        support=("Give the key idea in a word bank and a summary frame."),
        challenge=("Summarise {focus} in exactly ten words and defend the "
                   "word choices."),
        stages=("first", "repeat"),
        adaptation="Board notes serve as the source when there is one text.",
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
        if hint and (hint in activity.id or hint in activity.activity_types):
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
    "add": ("Check: learners add one unseen set of numbers for {focus} and "
            "show the working."),
    "subtract": ("Check: learners subtract one unseen item for {focus} and "
                 "check the answer by adding back."),
    "multiply": ("Check: learners multiply one unseen pair for {focus} and "
                 "show the working."),
    "divide": ("Check: learners divide one unseen item for {focus} and "
               "state the remainder or quotient."),
    "count": ("Check: learners count a fresh set for {focus} and record "
              "the total unprompted."),
    "install": ("Check: each learner completes the install of {focus} once "
                "on their own device or the shared one, following the "
                "stated steps."),
    "assess": ("Check: learners assess one sample for {focus} against the "
               "criteria and give a score with one reason."),
    "review": ("Check: learners review one piece of work on {focus} and "
               "name one strength and one improvement."),
    "relate": ("Check: learners relate {focus} to one real situation of "
               "their own and state the connection."),
    "recognise": ("Check: learners recognise {focus} in a fresh set of "
                  "examples, naming each one unprompted."),
    "sing": ("Check: each group sings {focus} once with correct words and "
             "beat, and one learner states the message."),
    "summarise": ("Check: learners summarise {focus} in one sentence in "
                  "their own words."),
    "summarize": ("Check: learners summarize {focus} in one sentence in "
                  "their own words."),
    "retell": ("Check: learners retell {focus} from the text with the two "
               "key facts intact."),
    "label": ("Check: learners label a fresh diagram of {focus} with at "
              "least four of five labels correct."),
    "locate": ("Check: learners locate the required places for {focus} on "
               "a fresh outline map, unprompted."),
    "sequence": ("Check: learners sequence the steps of {focus} in the "
                 "correct order and justify one fixed step."),
    "troubleshoot": ("Check: learners diagnose and fix one introduced "
                     "fault in {focus} and name the check that found it."),
    "observe": ("Check: learners record both required observations for "
                "{focus} accurately from their own notes."),
    "reflect": ("Check: learners write one way they will apply {focus} "
                "this week, with a reason."),
    "present": ("Check: each group presents {focus} with the product "
                "visible, two reasons and one answered question."),
    "critique": ("Check: learners critique {focus} against two criteria "
                 "and make one agreed improvement."),
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

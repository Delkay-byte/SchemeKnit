"""
SchemeKnit Subject Pedagogy Profiles
=====================================

The deterministic generation engine must not apply one generic activity recipe
to every subject. Each profile below describes how a lesson for that subject is
actually taught in a Ghanaian classroom: how it starts, the main learning
phases, how learning is assessed, which resources are realistic, and how to
differentiate.

Profiles are DATA, not behaviour. The lesson builder reads a profile and the
indicator interpretation to compose one coherent three-phase lesson:

    STARTER  → MAIN (instruction + guided practice + assessment opportunity)
             → PLENARY (reflection / consolidation)

Everything here is deterministic: the same curriculum input always produces the
same baseline lesson. Variety comes from the subject, the indicator's activity
type, and lesson position — never from randomness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass(frozen=True)
class MainPhase:
    """One MAIN phase. ``template`` uses the placeholders {skill} {topic}."""
    name: str
    template: str
    weight: float  # fraction of the MAIN block (sums to ~1.0)


@dataclass(frozen=True)
class SubjectPedagogy:
    key: str
    label: str
    starter_template: str
    main_phases: List[MainPhase]
    assessment_template: str
    plenary_template: str
    resources: List[str]
    support_template: str
    extension_template: str
    grouping: str
    keywords: List[str] = field(default_factory=list)
    essential_question: str = "What will we learn today and how will we know we have learned it?"
    pedagogy_note: str = ""


#: Placeholders available to every template:
#:   {skill}       — the indicator text with its code stripped
#:   {topic}       — strand - sub-strand
#:   {strand}      — strand
#:   {sub_strand}  — sub-strand
#:   {class_level} — e.g. "Basic 7"
#:   {prev}        — previous indicator text (may be empty)
#:   {next}        — next indicator text (may be empty)

_MATH = SubjectPedagogy(
    key="mathematics",
    label="Mathematics",
    starter_template=(
        "Activate prior knowledge with a quick mental/oral drill on the "
        "prerequisite skill for {skill}. Ask two learners to explain the last "
        "step they remember. Write one short example on the board and have the "
        "class say the answer together."
    ),
    main_phases=[
        MainPhase("Teacher demonstration (worked example)",
                  "Work through one fully-reasoned example of {skill} on the board, "
                  "thinking aloud at each step so learners see the reasoning, not "
                  "just the answer.", 0.30),
        MainPhase("Guided practice",
                  "Learners attempt a similar problem in pairs while the teacher "
                  "moves around the room checking each step of {skill}. Errors are "
                  "corrected on the spot.", 0.35),
        MainPhase("Independent practice and error analysis",
                  "Each learner solves 2-3 problems independently. The teacher "
                  "selects one common wrong answer and the class analyses why it is "
                  "wrong, relating it to {skill}.", 0.35),
    ],
    assessment_template=(
        "Written class exercise of 2-3 problems that test {skill}; mark for correct "
        "method and correct answer. Use the wrong answers to identify learners who "
        "need a guided re-teach next lesson."
    ),
    plenary_template=(
        "Ask learners to state the rule or method for {skill} in one sentence. "
        "Summarise the key steps on the board and set one similar problem as "
        "homework."
    ),
    resources=["chalkboard", "counting materials or counters", "number cards",
               "exercise books", "rulers"],
    support_template=(
        "Give struggling learners a partially completed worked example and "
        "counters/place-value cards so they can do {skill} concretely before "
        "writing it."
    ),
    extension_template=(
        "Ask confident learners to create and solve their own problem on {skill} "
        "and explain the method to a partner."
    ),
    grouping="Whole class for the worked example, then mixed-ability pairs for guided practice.",
    keywords=["operation", "method", "working"],
    essential_question="How do we show our reasoning clearly when solving this?",
    pedagogy_note="Concrete → pictorial → abstract. Always connect to a real-life context.",
)

_SCIENCE = SubjectPedagogy(
    key="science",
    label="Science",
    starter_template=(
        "Pose a short prediction question about {skill}: 'What do you think will "
        "happen, and why?' Collect two or three predictions on the board without "
        "judging them yet."
    ),
    main_phases=[
        MainPhase("Demonstration / guided inquiry",
                  "Demonstrate or set up the activity for {skill} using locally "
                  "available materials. Learners observe carefully and record what "
                  "they see or measure.", 0.40),
        MainPhase("Observation and evidence collection",
                  "In groups, learners carry out the activity for {skill}, record "
                  "results in a simple table, and note anything unexpected.", 0.35),
        MainPhase("Explanation",
                  "Groups explain their results against the earlier predictions. "
                  "The teacher corrects misconceptions and links findings to {skill}.", 0.25),
    ],
    assessment_template=(
        "Observe learners carrying out {skill} using a short checklist, then ask "
        "them to explain their result in writing. Check that the explanation "
        "matches the evidence, not a memorised answer."
    ),
    plenary_template=(
        "Return to the predictions made at the start: which were supported by the "
        "evidence? Summarise the key finding about {skill} and ask what learners "
        "would investigate next."
    ),
    resources=["locally available materials", "charts", "specimen or sample",
               "exercise books", "simple measuring tools"],
    support_template=(
        "Pair struggling learners with a supportive partner and give them a "
        "simplified observation table with sentence starters for {skill}."
    ),
    extension_template=(
        "Challenge confident learners to design a fair test or give a real-life "
        "example of {skill} not covered in class."
    ),
    grouping="Groups of 4-5 for the investigation, with whole-class explanation.",
    keywords=["investigation", "evidence", "observation", "result"],
    essential_question="What evidence shows that our explanation of this is correct?",
    pedagogy_note="Predict → observe → explain. Never assert a result the learners have not seen.",
)

_ENGLISH = SubjectPedagogy(
    key="english",
    label="English Language",
    starter_template=(
        "Warm up with quick oral language practice linked to {skill}: build a "
        "word wall or ask learners to say sentences aloud. Elicit what they "
        "already know about the language feature in focus."
    ),
    main_phases=[
        MainPhase("Model",
                  "Present a clear model/example of {skill}. Read it aloud and "
                  "highlight the feature being taught so learners can see and hear it.", 0.30),
        MainPhase("Guided language practice",
                  "Learners practise {skill} with the teacher's support — in pairs, "
                  "through substitution, role play, or guided reading/writing.", 0.40),
        MainPhase("Independent production",
                  "Each learner produces their own short piece of speaking, reading "
                  "or writing that uses {skill}. The teacher circulates and gives "
                  "immediate feedback.", 0.30),
    ],
    assessment_template=(
        "Assess the independent production task against a short checklist for "
        "{skill}. Also note oral contributions during guided practice for learners "
        "who struggle with writing."
    ),
    plenary_template=(
        "Ask two or three learners to share their work aloud. Correct common errors "
        "together, emphasise the target language feature for {skill}, and set a "
        "short follow-up task."
    ),
    resources=["textbook", "charts or word wall", "picture cards",
               "exercise books", "real objects"],
    support_template=(
        "Provide sentence frames/starters and a word bank so learners can produce "
        "{skill} with support."
    ),
    extension_template=(
        "Ask confident learners to extend their piece or peer-edit a partner's work "
        "focusing on {skill}."
    ),
    grouping="Whole class modelling, pairs for guided practice, individual production.",
    keywords=["language", "communication", "expression"],
    essential_question="How do we use language clearly and correctly for this purpose?",
    pedagogy_note="Model → guided practice → independent production, with feedback at every stage.",
)

_SOCIAL = SubjectPedagogy(
    key="social_studies",
    label="Social Studies",
    starter_template=(
        "Open with a familiar local scenario or question about {skill}. Ask "
        "learners to share what they already know from home and community life."
    ),
    main_phases=[
        MainPhase("Scenario / source study",
                  "Present a simple scenario, map, chart or case about {skill}. "
                  "Learners identify the key people, places or issues involved.", 0.35),
        MainPhase("Discussion",
                  "Organise a structured class/group discussion on {skill}. Guide "
                  "learners to give reasons and listen to other views.", 0.35),
        MainPhase("Application",
                  "Learners apply what they have discussed to a local situation, "
                  "answering 'what would we do here?'.", 0.30),
    ],
    assessment_template=(
        "Ask oral questions and set a short written task requiring learners to give "
        "a reason for a view on {skill}. Look for reasoning, not just recall."
    ),
    plenary_template=(
        "Summarise the main ideas about {skill} and connect them to learners' own "
        "community. Ask what responsibility each person has."
    ),
    resources=["maps", "charts", "chalkboard", "local examples/newspaper cutting",
               "exercise books"],
    support_template=(
        "Give struggling learners a sentence frame and pair them with a peer who "
        "can model answering about {skill}."
    ),
    extension_template=(
        "Ask confident learners to compare this with another community or to write "
        "a short argument about {skill}."
    ),
    grouping="Whole class scenario, small-group discussion, individual written task.",
    keywords=["community", "society", "responsibility", "reason"],
    essential_question="How does this affect people and communities in Ghana?",
    pedagogy_note="Start from the learner's own community and move outward.",
)

_CREATIVE = SubjectPedagogy(
    key="creative_arts",
    label="Creative Arts and Design",
    starter_template=(
        "Show or perform a short sample connected to {skill} and ask learners what "
        "they notice about how it was made or performed."
    ),
    main_phases=[
        MainPhase("Observation and demonstration",
                  "Demonstrate the technique/material process for {skill}. Learners "
                  "watch closely and identify the steps.", 0.30),
        MainPhase("Creation",
                  "Learners create their own work applying {skill}, using locally "
                  "available materials. The teacher supports individuals.", 0.50),
        MainPhase("Critique and reflection",
                  "Learners display or perform their work. Peers give kind, specific "
                  "feedback relating to {skill}.", 0.20),
    ],
    assessment_template=(
        "Assess the created work or performance against a simple rubric for {skill} "
        "(technique, effort, expression), plus learners' own reflection."
    ),
    plenary_template=(
        "Celebrate a few examples, summarise the key technique in {skill}, and ask "
        "learners what they would improve next time."
    ),
    resources=["locally available materials", "colours/pigments", "paper",
               "simple tools", "instruments or props"],
    support_template=(
        "Provide partially prepared materials or a simple pattern so learners can "
        "succeed at {skill} while still doing the creative work themselves."
    ),
    extension_template=(
        "Invite confident learners to add a personal variation or a more complex "
        "piece demonstrating {skill}."
    ),
    grouping="Whole-class demonstration, individual creation, peer critique in small groups.",
    keywords=["technique", "creation", "expression", "critique"],
    essential_question="How do we create or perform this skilfully?",
    pedagogy_note="Demonstrate → create → critique. Use local materials; never assume expensive supplies.",
)

_ICT = SubjectPedagogy(
    key="ict",
    label="ICT / Computing",
    starter_template=(
        "Recall the last ICT skill learned and connect it to {skill}. If devices "
        "are limited, use an unplugged analogy from everyday life."
    ),
    main_phases=[
        MainPhase("Demonstration / explanation",
                  "Demonstrate the concept or steps for {skill}. Use the board or an "
                  "unplugged model if there are not enough devices for everyone.", 0.35),
        MainPhase("Guided hands-on practice",
                  "Learners practise {skill} in small groups taking turns, or on "
                  "paper/board using the same steps where devices are shared.", 0.40),
        MainPhase("Challenge task",
                  "Learners complete a short task applying {skill} on their own and "
                  "troubleshoot one common problem.", 0.25),
    ],
    assessment_template=(
        "Observe learners performing {skill} against a steps checklist, or mark a "
        "paper-based version where devices are not available."
    ),
    plenary_template=(
        "Review the steps for {skill}, discuss the common problem met and how it "
        "was solved, and link to everyday technology."
    ),
    resources=["computers (shared if limited)", "unplugged activity materials",
               "diagrams/flowcharts", "chalkboard", "exercise books"],
    support_template=(
        "Pair learners who need help with a peer 'digital buddy' and provide a "
        "numbered step card for {skill}."
    ),
    extension_template=(
        "Ask confident learners to help a peer or to apply {skill} to a slightly "
        "harder task."
    ),
    grouping="Whole-class demonstration, small groups at shared devices, individual task.",
    keywords=["steps", "process", "digital", "troubleshoot"],
    essential_question="What are the correct steps, and what do we do when something goes wrong?",
    pedagogy_note="Plan for few or no devices: pair the digital task with an unplugged equivalent.",
)

_RME = SubjectPedagogy(
    key="rme",
    label="Religious and Moral Education",
    starter_template=(
        "Begin with a short story, proverb or real-life situation linked to {skill}. "
        "Ask learners what lessons people can learn from it."
    ),
    main_phases=[
        MainPhase("Story / teaching",
                  "Present the story, teaching or belief connected to {skill}, "
                  "respecting the diverse beliefs in the class.", 0.30),
        MainPhase("Discussion of values",
                  "Guide learners to discuss the moral values and choices in {skill}, "
                  "giving reasons and respecting different views.", 0.40),
        MainPhase("Application to life",
                  "Learners relate {skill} to a decision they might face and explain "
                  "what a good choice would be and why.", 0.30),
    ],
    assessment_template=(
        "Ask oral questions and set a short written reflection in which learners "
        "justify a moral choice connected to {skill}. Value reasoning, not recall."
    ),
    plenary_template=(
        "Summarise the values in {skill} and invite learners to name one way they "
        "will apply it this week."
    ),
    resources=["source text or story", "charts", "real-life scenarios",
               "chalkboard", "exercise books"],
    support_template=(
        "Offer a sentence frame and a simple example so learners can express their "
        "reasoning about {skill}."
    ),
    extension_template=(
        "Ask confident learners to compare the teaching in {skill} with another "
        "tradition or life situation."
    ),
    grouping="Whole-class story and discussion, individual reflection.",
    keywords=["values", "choice", "respect", "responsibility"],
    essential_question="What is the right thing to do, and why?",
    pedagogy_note="Respect diverse beliefs; focus on reasons and values, never on one tradition as the only truth.",
)

_PHE = SubjectPedagogy(
    key="phe",
    label="Physical and Health Education",
    starter_template=(
        "Lead a short warm-up related to {skill} and check that the space is safe. "
        "Explain why warming up matters for this activity."
    ),
    main_phases=[
        MainPhase("Demonstration",
                  "Demonstrate the movement, skill or health practice for {skill}, "
                  "emphasising safety and correct technique.", 0.30),
        MainPhase("Guided practice",
                  "Learners practise {skill} in small groups or pairs, with the "
                  "teacher giving feedback on technique.", 0.45),
        MainPhase("Application / game",
                  "Learners apply {skill} in a simple game, drill or routine.", 0.25),
    ],
    assessment_template=(
        "Observe learners performing {skill} against a short technique/safety "
        "checklist; ask one or two learners to explain why the practice matters."
    ),
    plenary_template=(
        "Cool down, review the key technique and safety points for {skill}, and "
        "discuss how it helps health and fitness."
    ),
    resources=["safe open space", "cones or markers", "ball or improvised equipment",
               "whistle", "water"],
    support_template=(
        "Offer a slower version of the activity and extra verbal cues so learners "
        "can succeed at {skill} safely."
    ),
    extension_template=(
        "Challenge confident learners to lead a short practice or add a harder "
        "variation of {skill}."
    ),
    grouping="Whole-class warm-up, small groups for practice, applied game.",
    keywords=["technique", "safety", "fitness", "health"],
    essential_question="How do we perform this safely and why does it matter for health?",
    pedagogy_note="Always warm up, check the space and emphasise safety.",
)

_CAREER = SubjectPedagogy(
    key="career_technology",
    label="Career Technology",
    starter_template=(
        "Show/name the raw materials or tools connected to {skill} and ask learners "
        "what they could be used to make."
    ),
    main_phases=[
        MainPhase("Materials and demonstration",
                  "Identify the materials and demonstrate the process for {skill}, "
                  "emphasising safe use of any tools.", 0.30),
        MainPhase("Practical activity",
                  "Learners carry out the practical task for {skill} using locally "
                  "available materials, working safely.", 0.50),
        MainPhase("Reflection",
                  "Learners inspect and evaluate the product, discussing what worked "
                  "and what could improve.", 0.20),
    ],
    assessment_template=(
        "Assess the finished product or process for {skill} against a short rubric "
        "(correct steps, safety, quality), plus learners' reflection."
    ),
    plenary_template=(
        "Review the process for {skill}, emphasise safe practice, and discuss how "
        "the skill is used in real work."
    ),
    resources=["locally available raw materials", "simple tools",
               "safety equipment as needed", "work surface", "exercise books"],
    support_template=(
        "Break the task into smaller labelled steps and pair learners so they can "
        "complete {skill} with support."
    ),
    extension_template=(
        "Ask confident learners to improve the design or make a second, better "
        "version applying {skill}."
    ),
    grouping="Whole-class demonstration, small-group practical work.",
    keywords=["process", "materials", "safety", "product"],
    essential_question="How is this made or done correctly and safely?",
    pedagogy_note="Use locally available materials and always teach safe tool use.",
)

_EARLY = SubjectPedagogy(
    key="early_childhood",
    label="KG / Early Childhood",
    starter_template=(
        "Begin with a short song, rhyme or movement activity linked to {skill}. "
        "Use concrete objects and picture cards to gain attention."
    ),
    main_phases=[
        MainPhase("Teacher-led activity",
                  "Show and model {skill} with real objects, using simple language "
                  "and repetition. Invite children to join in.", 0.35),
        MainPhase("Play-based practice",
                  "Children practise {skill} through play, songs, sorting or games "
                  "in small groups while the teacher supports.", 0.45),
        MainPhase("Individual try",
                  "Each child tries the activity or task for {skill} with the "
                  "teacher's encouragement.", 0.20),
    ],
    assessment_template=(
        "Observe children during play and the individual try, using a simple "
        "checklist for {skill}. Note who needs more practice; there is no written test."
    ),
    plenary_template=(
        "Gather the children, sing or clap about {skill}, and praise specific "
        "efforts. Pack away together."
    ),
    resources=["real objects", "picture cards", "song/rhyme", "play materials",
               "floor space"],
    support_template=(
        "Give extra one-to-one help and larger, simpler materials so the child can "
        "try {skill} successfully."
    ),
    extension_template=(
        "Offer confident children a slightly harder version or let them show a "
        "friend how to do {skill}."
    ),
    grouping="Whole-group circle time, then small play groups.",
    keywords=["play", "song", "practice"],
    essential_question="What are we learning through playing today?",
    pedagogy_note="Everything is concrete and play-based; keep activities short and lively.",
)

_NURSERY = SubjectPedagogy(
    key="nursery",
    label="Nursery",
    starter_template=(
        "Gather the children with a familiar song or rhyme, then show the real "
        "objects or pictures for {skill} and let them touch and talk about them."
    ),
    main_phases=[
        MainPhase("Teacher modelling",
                  "Model {skill} slowly with real objects while the children "
                  "watch, listen and repeat after you.", 0.30),
        MainPhase("Guided participation",
                  "Guide the children to try {skill} themselves, one small step "
                  "at a time, helping each child by name.", 0.40),
        MainPhase("Playful practice",
                  "Let the children play at {skill} in small groups — sorting, "
                  "matching, singing or colouring — while you watch and "
                  "encourage them.", 0.30),
    ],
    assessment_template=(
        "Watch each child during the activity and ask simple oral questions — "
        "point to, name or show {skill}. Tick who can do it and who needs more "
        "help; there is no written test."
    ),
    plenary_template=(
        "Bring the children back to the circle, sing or clap about {skill}, let "
        "a few children show what they made or did, and praise each child."
    ),
    resources=["charts & pictures", "counters", "flash cards", "colours",
               "real objects"],
    support_template=(
        "Sit beside the child, guide the hand or the answer for {skill}, and "
        "use bigger, simpler objects until the child succeeds."
    ),
    extension_template=(
        "Let children who finish early do {skill} again with more objects or "
        "show a friend how it is done."
    ),
    grouping="Whole-class circle time, then small guided groups.",
    keywords=["objects", "play", "oral"],
    essential_question="What can each child do or say about {skill} today?",
    pedagogy_note=(
        "Oral instruction, concrete objects, imitation, play and praise; keep "
        "every activity short and repeat it often."
    ),
)

_GENERIC = SubjectPedagogy(
    key="generic",
    label="General",
    starter_template=(
        "Activate prior knowledge for {skill} with a short oral question-and-answer "
        "session. Link today's lesson to the previous one."
    ),
    main_phases=[
        MainPhase("Teacher explanation",
                  "Introduce and explain {skill} clearly, using the board and "
                  "examples from learners' own experience.", 0.35),
        MainPhase("Guided practice",
                  "Learners practise {skill} with the teacher's support in pairs or "
                  "small groups.", 0.40),
        MainPhase("Independent application",
                  "Learners apply {skill} on their own while the teacher gives "
                  "feedback.", 0.25),
    ],
    assessment_template=(
        "Ask oral questions and set a short task that tests {skill}; use the "
        "responses to plan the next lesson."
    ),
    plenary_template=(
        "Summarise the key points of {skill}, ask learners what they learned, and "
        "set a short follow-up task."
    ),
    resources=["chalkboard", "charts", "locally available materials",
               "exercise books"],
    support_template=(
        "Provide a simpler version of the task and extra guidance so learners can "
        "make progress with {skill}."
    ),
    extension_template=(
        "Offer a more challenging task or question that applies {skill} in a new way."
    ),
    grouping="Whole class, then pairs or small groups.",
    keywords=[],
    essential_question="What will we learn today and how will we know we have learned it?",
)


SUBJECT_PROFILES = {
    p.key: p for p in [
        _MATH, _SCIENCE, _ENGLISH, _SOCIAL, _CREATIVE, _ICT, _RME, _PHE,
        _CAREER, _EARLY, _NURSERY, _GENERIC,
    ]
}

#: Subject value (lowercased) → profile key. Specific before generic.
SUBJECT_TO_PROFILE = {
    "mathematics": "mathematics",
    "core mathematics": "mathematics",
    "elective mathematics": "mathematics",
    "numeracy": "mathematics",
    "science": "science",
    "integrated science": "science",
    "biology": "science",
    "chemistry": "science",
    "physics": "science",
    "general agriculture": "science",
    "english language": "english",
    "english": "english",
    "literature in english": "english",
    "ghanaian language": "english",
    "french": "english",
    "social studies": "social_studies",
    "economics": "social_studies",
    "geography": "social_studies",
    "government": "social_studies",
    "history": "social_studies",
    "our world our people": "social_studies",
    "creative arts and design": "creative_arts",
    "creative arts": "creative_arts",
    "general knowledge in art": "creative_arts",
    "ict": "ict",
    "computing": "ict",
    "religious and moral education": "rme",
    "rme": "rme",
    "physical and health education": "phe",
    "physical development": "phe",
    "career technology": "career_technology",
    "business management": "career_technology",
    "financial accounting": "career_technology",
    "cost accounting": "career_technology",
    "language and literacy": "early_childhood",
}


def profile_for_subject(subject: str) -> SubjectPedagogy:
    """Return the pedagogy profile for a subject name (never None)."""
    key = SUBJECT_TO_PROFILE.get((subject or "").strip().lower())
    if key and key in SUBJECT_PROFILES:
        return SUBJECT_PROFILES[key]
    return _GENERIC

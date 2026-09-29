"""
English Language — derived exemplar records (NaCCA CCP, Basic 7).

Derived from the official *English Language Common Core Programme (CCP)*
curriculum, NaCCA / Ministry of Education, 2021 — Strand 1 (Oral Language:
Listening and Speaking), Sub-strand 1 (Conversation/Everyday Discourse).
Derived information only; no official text stored.
"""

from __future__ import annotations

from typing import List

from . import ExemplarRecord

_SOURCE = dict(
    source_title=(
        "English Language Curriculum for Basic 7–10, Common Core Programme "
        "(CCP), NaCCA / Ministry of Education, Ghana"
    ),
    source_url="https://nacca.gov.gh/wp-content/uploads/2022/10/English-Language.pdf",
    source_version="NaCCA/Ministry of Education 2021 (CCP, Basic 7–10)",
)

_STRAND = "Oral Language (Listening and Speaking)"
_SUB_STRAND = "Conversation/Everyday Discourse"

RECORDS: List[ExemplarRecord] = [
    ExemplarRecord(
        subject="English Language",
        level="B7",
        strand=_STRAND,
        sub_strand=_SUB_STRAND,
        content_standard_code="B7/JHS1.1.1.1",
        indicator_code="B7/JHS1.1.1.1.1",
        learning_focus="Using formal and informal register in conversation",
        curriculum_action_verbs=["identify", "use", "participate"],
        exemplar_activity_patterns=[
            "Play or read out two short exchanges — one between a learner and a "
            "head teacher, one between two friends. Ask learners which one is "
            "formal and how they can tell, and list their clues on the board.",
            "Model a formal exchange (greeting, request, closing) and a casual one. "
            "Learners identify the words that made each one formal or informal and "
            "note them under the two headings.",
            "In pairs, learners hold a two-minute conversation in a situation from a "
            "card the teacher gives (school office, market, bus station), keeping "
            "to the correct register. Two pairs perform for the class.",
        ],
        assessment_patterns=[
            "Listen to each pair's conversation and check no slang or contracted "
            "slang forms are used in the formal situations.",
            "Ask a learner to name one word that marks formal language and one that "
            "marks informal language.",
        ],
        assignment_patterns=[
            "Write a short formal exchange between you and your head teacher about "
            "a school matter, then rewrite it as a conversation with a close friend.",
            "List five informal words or slang terms you use with friends and give "
            "the formal equivalent for each.",
        ],
        class_assignment_pattern=(
            "Pairs hold a two-minute conversation for a situation given on a card, "
            "keeping to the correct register. The teacher listens for register "
            "control and asks two pairs to perform before the class, then the class "
            "names the formal markers used."
        ),
        home_assignment_pattern=(
            "Write one formal and one informal exchange on the same topic (for "
            "example asking for directions). Underline the words that show the "
            "register in each exchange."
        ),
        suitable_resource_patterns=[
            "situation cards (school office, market, bus station, classroom)",
            "chart headed FORMAL / INFORMAL for learners' contributions",
        ],
        focus_terms=[
            "register", "formal language", "informal language", "conversation",
            "greetings", "requests", "slang",
        ],
        core_competencies=[
            "Communication and Collaboration",
            "Personal Development and Leadership",
        ],
        provenance=(
            "Derived by SchemeKnit from the official NaCCA English Language CCP "
            "exemplars for B7/JHS1.1.1.1.1 (identify formal and informal "
            "situations; use appropriate language in each; greetings, requests, "
            "encouragements, partings; avoid slang in formal contexts)."
        ),
        **_SOURCE,
    ),
    ExemplarRecord(
        subject="English Language",
        level="B7",
        strand=_STRAND,
        sub_strand=_SUB_STRAND,
        content_standard_code="B7/JHS1.1.1.1",
        indicator_code="B7/JHS1.1.1.1.2",
        learning_focus="Questioning to elicit elaboration in conversation",
        curriculum_action_verbs=["identify", "ask", "respond"],
        exemplar_activity_patterns=[
            "Ask one learner a closed question ('Do you like football?') and note "
            "how short the answer is. Then ask 'Why do you think so?' and show how "
            "the answer grows.",
            "Write up the elaboration words why, how and for what reason. Model a "
            "short exchange where a questioner uses each one and the partner "
            "answers with reasons.",
            "In pairs, learners take turns being the questioner and the responder on "
            "a topic from the board, using at least two elaboration words each. The "
            "pair then reports one idea their partner elaborated.",
        ],
        assessment_patterns=[
            "Listen for whether the questioner uses why/how and whether the "
            "responder gives a reason rather than a yes or no.",
            "Ask a learner to turn a closed question into a question that will "
            "elicit elaboration.",
        ],
        assignment_patterns=[
            "Write a conversation of six turns in which one speaker uses why, how "
            "and for what reason to get longer answers.",
            "Interview a family member about a topic you choose; write the questions "
            "you asked and the elaborations you received.",
        ],
        class_assignment_pattern=(
            "In pairs, learners hold a conversation where the questioner must use "
            "at least two elaboration words and the responder must give reasons. "
            "The teacher listens for elaboration and asks pairs to report one idea "
            "their partner gave."
        ),
        home_assignment_pattern=(
            "Interview one adult at home about a topic of your choice. Write the "
            "questions you asked (using why, how or for what reason) and the "
            "answers you received."
        ),
        suitable_resource_patterns=[
            "board list of elaboration question words",
            "sentence starters for reasoned answers",
        ],
        focus_terms=[
            "elaboration", "questions", "reasons", "conversation",
            "response",
        ],
        core_competencies=[
            "Communication and Collaboration",
            "Critical Thinking and Problem Solving",
        ],
        provenance=(
            "Derived by SchemeKnit from the official NaCCA English Language CCP "
            "exemplars for B7/JHS1.1.1.1.2 (identify words that elicit elaboration "
            "— why, how, for what reason; engage in conversation using them; "
            "respond to others' questions)."
        ),
        **_SOURCE,
    ),
]

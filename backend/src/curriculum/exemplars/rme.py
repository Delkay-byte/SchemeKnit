"""
Religious and Moral Education — derived exemplar records (NaCCA CCP, Basic 7).

Derived from the official *Religious and Moral Education Common Core Programme
(CCP)* curriculum, NaCCA / Ministry of Education, 2021 — Strand 1 (God, His
Creation and Attributes), Sub-strand 1 (God, His Nature and Attributes).
Derived information only; no official text stored.
"""

from __future__ import annotations

from typing import List

from . import ExemplarRecord

_SOURCE = dict(
    source_title=(
        "Religious and Moral Education Curriculum for B7/JHS1–B9/JHS3, Common "
        "Core Programme (CCP), NaCCA / Ministry of Education, Ghana"
    ),
    source_url=(
        "https://nacca.gov.gh/wp-content/uploads/2022/10/"
        "Religious-and-Moral-Education.pdf"
    ),
    source_version="NaCCA/Ministry of Education 2021 (CCP, Basic 7–9)",
)

_STRAND = "God, His Creation and Attributes"
_SUB_STRAND = "God, His Nature and Attributes"

RECORDS: List[ExemplarRecord] = [
    ExemplarRecord(
        subject="Religious and Moral Education",
        level="B7",
        strand=_STRAND,
        sub_strand=_SUB_STRAND,
        content_standard_code="B7/JHS1 1.1.1",
        indicator_code="B7/JHS1 1.1.1.1",
        learning_focus="Attributes of God in the three major religions",
        curriculum_action_verbs=["identify", "explain", "write"],
        exemplar_activity_patterns=[
            "Ask learners to describe someone they respect. Collect the qualities "
            "they name on the board, then introduce the idea that these are "
            "attributes of a person, and God has attributes too.",
            "Name the attributes of God (omnipotent, omnipresent, omniscient, love, "
            "patience) one at a time. For each, ask learners what it means and "
            "record their explanations beside the word.",
            "In groups, learners find the local-language names used for God in at "
            "least two Ghanaian languages and write what each name says about His "
            "nature, then share with the class.",
        ],
        assessment_patterns=[
            "Ask a learner to name an attribute of God and explain it in one "
            "sentence of their own.",
            "Check each group's list gives the attribute and its meaning, not only "
            "the word.",
        ],
        assignment_patterns=[
            "Write a short paragraph explaining three attributes of God and what "
            "each one means to you.",
            "Ask an elder at home for one local name for God and write what it "
            "means.",
        ],
        class_assignment_pattern=(
            "In groups, learners list at least four attributes of God with the "
            "meaning of each, and add one local-language name for God with its "
            "meaning. The teacher checks each group explains the attributes rather "
            "than only naming them."
        ),
        home_assignment_pattern=(
            "Explain three attributes of God in your own words. For each one, give "
            "one way a person can show that attribute in daily life."
        ),
        suitable_resource_patterns=[
            "chart listing the attributes of God",
            "copies of the sacred texts of the three major religions (where available)",
        ],
        focus_terms=[
            "attributes of God", "omnipotent", "omnipresent", "omniscient",
            "nature of God", "the three major religions",
        ],
        core_competencies=[
            "Cultural Identity and Global Citizenship",
            "Critical Thinking and Problem Solving",
            "Communication and Collaboration",
        ],
        provenance=(
            "Derived by SchemeKnit from the official NaCCA RME CCP exemplars for "
            "B7/JHS1 1.1.1.1 (identify the attributes of God; explain them in "
            "English and in local languages; write on the attributes of God for "
            "class discussion, drawing on the three major religions)."
        ),
        **_SOURCE,
    ),
    ExemplarRecord(
        subject="Religious and Moral Education",
        level="B7",
        strand=_STRAND,
        sub_strand=_SUB_STRAND,
        content_standard_code="B7/JHS1 1.1.1",
        indicator_code="B7/JHS1 1.1.1.2",
        learning_focus="Demonstrating the attributes of God in daily life",
        curriculum_action_verbs=["identify", "role play", "describe"],
        exemplar_activity_patterns=[
            "Ask learners which qualities of God they can also show as human "
            "beings. Collect their answers (love, patience, mercy) on the board.",
            "Model one short scene where a person shows patience in a difficult "
            "moment, then ask learners to name the attribute being shown.",
            "In small groups, learners role play a situation where they show one "
            "attribute of God toward another person, then the class names the "
            "attribute each group demonstrated.",
        ],
        assessment_patterns=[
            "After each role play, ask the class to name the attribute shown and "
            "give the reason from what they saw.",
            "Ask a learner to describe one thing they will do differently to show "
            "an attribute of God at home.",
        ],
        assignment_patterns=[
            "Describe one situation where you showed patience or love and explain "
            "how it reflects the nature of God.",
            "Write three ways you can show an attribute of God at home this week.",
        ],
        class_assignment_pattern=(
            "In small groups, learners role play a situation in which they show one "
            "attribute of God and the class names the attribute with a reason. The "
            "teacher checks each group's scene genuinely demonstrates the attribute."
        ),
        home_assignment_pattern=(
            "Choose one attribute of God. Describe a situation at home where you "
            "can show it and write what you will actually do."
        ),
        suitable_resource_patterns=[
            "chart of attributes of God",
            "everyday classroom objects to set up the role-play situation",
        ],
        focus_terms=[
            "attributes of God", "patience", "mercy", "love", "humankind",
            "role play",
        ],
        core_competencies=[
            "Personal Development and Leadership",
            "Cultural Identity and Global Citizenship",
            "Communication and Collaboration",
        ],
        provenance=(
            "Derived by SchemeKnit from the official NaCCA RME CCP exemplars for "
            "B7/JHS1 1.1.1.2 (identify the attributes of God found in humankind; "
            "role play how these attributes relate to the learner's own life)."
        ),
        **_SOURCE,
    ),
]

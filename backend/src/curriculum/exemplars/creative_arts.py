"""
Creative Arts and Design — derived exemplar records (NaCCA CCP, Basic 7).

Derived from the official *Creative Arts and Design Common Core Programme (CCP)*
curriculum, NaCCA / Ministry of Education, 2021 — Strand 1 (Design), Sub-strand
1.1 (Design in Nature and Manmade Environment). Derived information only.
"""

from __future__ import annotations

from typing import List

from . import ExemplarRecord

_SOURCE = dict(
    source_title=(
        "Creative Arts and Design Curriculum for Basic 7–10, Common Core "
        "Programme (CCP), NaCCA / Ministry of Education, Ghana"
    ),
    source_url=(
        "https://nacca.gov.gh/wp-content/uploads/2022/10/"
        "Creative-Arts-and-Designs.pdf"
    ),
    source_version="NaCCA/Ministry of Education 2021 (CCP, Basic 7–10)",
)

RECORDS: List[ExemplarRecord] = [
    ExemplarRecord(
        subject="Creative Arts and Design",
        level="B7",
        strand="Design",
        sub_strand="Design in Nature and Manmade Environment",
        content_standard_code="B7/JHS1 1.1.1",
        indicator_code="B7/JHS1 1.1.1.1",
        learning_focus="Design in nature and the manmade environment",
        curriculum_action_verbs=["research", "identify", "reflect", "record"],
        exemplar_activity_patterns=[
            "Display two images — one natural form (a leaf or a bird's beak) and "
            "one manmade object (a chair or a building). Ask learners what the "
            "manmade object borrowed from nature and record their ideas.",
            "Explain the elements (dots, lines, shapes) and principles (balance, "
            "rhythm, repetition) of design using the two images, naming each one as "
            "learners point to where they can see it.",
            "In groups, learners find and sketch one natural form and one manmade "
            "form in or near the classroom, then write how the natural form may "
            "have influenced the manmade one.",
        ],
        assessment_patterns=[
            "Ask learners to name one element and one principle of design and point "
            "to each in their own sketch.",
            "Check each group's writing links a specific natural feature to a "
            "specific manmade feature.",
        ],
        assignment_patterns=[
            "Sketch one natural object and one manmade object at home and write how "
            "they are similar.",
            "Write a short reflection on the meaning, importance and role of design "
            "in your own environment.",
        ],
        class_assignment_pattern=(
            "In groups, learners sketch one natural and one manmade form, then "
            "write how the natural form influenced the manmade one. The teacher "
            "checks the sketch labels one element and one principle of design and "
            "that the writing names specific features."
        ),
        home_assignment_pattern=(
            "Sketch one natural object and one manmade object you can see at home. "
            "Write three sentences on how design in nature has influenced the "
            "manmade object."
        ),
        suitable_resource_patterns=[
            "pictures of natural forms and manmade designs",
            "drawing paper, pencils and colours",
            "real leaves, seeds or shells for direct observation",
        ],
        focus_terms=[
            "design", "natural forms", "manmade environment", "elements of design",
            "principles of design", "dots and lines", "shapes", "balance", "rhythm",
        ],
        core_competencies=[
            "Creativity and Innovation",
            "Critical Thinking and Problem Solving",
            "Communication and Collaboration",
            "Digital Literacy",
        ],
        provenance=(
            "Derived by SchemeKnit from the official NaCCA Creative Arts and "
            "Design CCP exemplars for B7/JHS1 1.1.1.1 (research and record the "
            "meaning, importance and role of design; identify and reflect on "
            "natural and manmade designs to see how nature influences manmade "
            "design)."
        ),
        **_SOURCE,
    ),
]

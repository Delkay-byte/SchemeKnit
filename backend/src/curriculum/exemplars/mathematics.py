"""
Mathematics — derived exemplar records (NaCCA CCP, Basic 7).

Derived from the official *Mathematics Common Core Programme (CCP)* curriculum,
NaCCA / Ministry of Education, 2021 — Strand 1 (Number), Sub-strand 1 (Number
and Numeration Systems). Derived information only; no official text stored.
"""

from __future__ import annotations

from typing import List

from . import ExemplarRecord

_SOURCE = dict(
    source_title=(
        "Mathematics Curriculum for Basic 7–10, Common Core Programme (CCP), "
        "NaCCA / Ministry of Education, Ghana"
    ),
    source_url="https://nacca.gov.gh/wp-content/uploads/2023/06/MATHEMATICS.pdf",
    source_version="NaCCA/Ministry of Education 2021 (CCP, Basic 7–10)",
)

RECORDS: List[ExemplarRecord] = [
    ExemplarRecord(
        subject="Mathematics",
        level="B7",
        strand="Number",
        sub_strand="Number and Numeration Systems",
        content_standard_code="B7.1.1.1",
        indicator_code="B7.1.1.1.1",
        learning_focus="Place value up to one billion",
        curriculum_action_verbs=["model", "represent", "determine"],
        exemplar_activity_patterns=[
            "Ask learners to read a seven-digit number written on the board and "
            "say what each digit is worth. Record the place-value names they give.",
            "Build a billion on the board with multi-base blocks or drawn flats "
            "(one cube = 100,000, one rod = 1,000,000, a flat = 10,000,000, a "
            "block = 100,000,000). Ask learners how many blocks make one billion "
            "and let them count the rods to check.",
            "In pairs, learners write a number greater than one billion in two "
            "different ways using multiples of 10, 50, 100 and 200 — every figure "
            "used at least once — then read their number to another pair.",
        ],
        assessment_patterns=[
            "Give each learner one number in the billions to write and read, and "
            "mark for correct place-value names and correct grouping.",
            "Ask learners to explain why 10 millions make one billion using the rods.",
        ],
        assignment_patterns=[
            "Write two different ways of making a number greater than one billion "
            "using multiples of 10, 50, 100 and 200.",
            "Write a number in the billions and state the value of each digit.",
        ],
        class_assignment_pattern=(
            "In pairs, learners represent two numbers greater than one billion "
            "using multiples of 10, 50, 100 and 200, and write the value of each "
            "digit in the number. The teacher checks the place-value names and "
            "whether every figure was used."
        ),
        home_assignment_pattern=(
            "Ask an adult for one large number written in their work (a price, a "
            "population or a distance). Write the number and state the value of "
            "each digit."
        ),
        suitable_resource_patterns=[
            "multi-base blocks or drawn flats, rods and cubes",
            "graph sheets or isometric papers",
            "place-value chart up to billions",
        ],
        focus_terms=[
            "place value", "one billion", "base ten", "multi-base blocks",
            "graph sheet", "numerals",
        ],
        core_competencies=[
            "Critical Thinking and Problem Solving",
            "Communication and Collaboration",
        ],
        provenance=(
            "Derived by SchemeKnit from the official NaCCA Mathematics CCP "
            "exemplars for B7.1.1.1.1 (model quantities above one billion with "
            "graph sheets, isometric paper and multi-base blocks; determine how "
            "many blocks make a billion; represent numbers in multiple ways)."
        ),
        **_SOURCE,
    ),
]

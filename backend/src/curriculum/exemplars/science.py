"""
Science — derived exemplar records (NaCCA CCP, Basic 7).

Derived from the official *Science Common Core Programme (CCP)* curriculum,
NaCCA / Ministry of Education, 2021 — Strand 1 (Diversity of Matter),
Sub-strand 1 (Materials). Derived information only; no official text stored.
"""

from __future__ import annotations

from typing import List

from . import ExemplarRecord

_SOURCE = dict(
    source_title=(
        "Science Curriculum for Basic 7–10, Common Core Programme (CCP), "
        "NaCCA / Ministry of Education, Ghana"
    ),
    source_url="https://nacca.gov.gh/wp-content/uploads/2022/10/Science-Curriculum.pdf",
    source_version="NaCCA/Ministry of Education 2021 (CCP, Basic 7–10)",
)

RECORDS: List[ExemplarRecord] = [
    ExemplarRecord(
        subject="Science",
        level="B7",
        strand="Diversity of Matter",
        sub_strand="Materials",
        content_standard_code="B7/JHS1.1.1.1",
        indicator_code="B7/JHS1.1.1.1.1",
        learning_focus="Classifying materials as solids, liquids and gases",
        curriculum_action_verbs=["classify", "record", "discuss", "give examples"],
        exemplar_activity_patterns=[
            "Hold up three items collected locally (a stone, a bottle of water, an "
            "empty sealed bottle). Ask learners how they would group them and "
            "record their groupings on the board.",
            "Hand each group the same set of materials. Learners examine and record "
            "the texture, appearance, colour and shape of each item in a table on "
            "the board, then group the items as solid, liquid or gas.",
            "Groups name one example of a solid, a liquid and a gas they can find "
            "in the school compound and explain to the class what made each one "
            "fit its group.",
        ],
        assessment_patterns=[
            "Check each group's completed table is accurate for texture, "
            "appearance, colour and shape.",
            "Ask individual learners to name one solid, one liquid and one gas from "
            "their own environment and give a reason.",
        ],
        assignment_patterns=[
            "List five materials from your home and write whether each is a solid, "
            "a liquid or a gas.",
            "Observe one liquid and one solid at home and write two differences you "
            "notice.",
        ],
        class_assignment_pattern=(
            "Groups complete a recording table for the supplied materials (texture, "
            "appearance, colour, shape) and classify each item as solid, liquid or "
            "gas. The teacher checks the recorded observations against the real "
            "materials and asks each group to defend one borderline item."
        ),
        home_assignment_pattern=(
            "Choose three materials at home — one solid, one liquid and one gas. "
            "Write what you observed about each and why you placed it in that group."
        ),
        suitable_resource_patterns=[
            "locally assembled materials (stone, water, sealed empty bottle, sand)",
            "recording table drawn on the board or on paper",
            "hand lens where available",
        ],
        focus_terms=[
            "solids", "liquids", "gases", "texture", "appearance", "particles",
            "properties of matter",
        ],
        core_competencies=[
            "Critical Thinking and Problem Solving",
            "Creativity and Innovation",
            "Communication and Collaboration",
        ],
        provenance=(
            "Derived by SchemeKnit from the official NaCCA Science CCP exemplars "
            "for B7/JHS1.1.1.1.1 (record texture, appearance, colour and shape in a "
            "table; group materials as liquids, solids and gases; discuss their "
            "differences; give local examples)."
        ),
        **_SOURCE,
    ),
]

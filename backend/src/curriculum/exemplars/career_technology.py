"""
Career Technology — derived exemplar records (NaCCA CCP, Basic 7).

Derived from the official *Career Technology Common Core Programme (CCP)*
curriculum, NaCCA / Ministry of Education, 2021 — Strand 1 (Personal Hygiene
and Food Hygiene). Derived information only; no official text stored.
"""

from __future__ import annotations

from typing import List

from . import ExemplarRecord

_SOURCE = dict(
    source_title=(
        "Career Technology Curriculum for Basic 7–10, Common Core Programme "
        "(CCP), NaCCA / Ministry of Education, Ghana"
    ),
    source_url="https://nacca.gov.gh/wp-content/uploads/2022/10/Career-Technology.pdf",
    source_version="NaCCA/Ministry of Education 2021 (CCP, Basic 7–10)",
)

RECORDS: List[ExemplarRecord] = [
    ExemplarRecord(
        subject="Career Technology",
        level="B7",
        strand="Personal Hygiene and Food Hygiene",
        sub_strand="Personal Hygiene and Food Hygiene",
        content_standard_code="B7/JHS1.1.1.1",
        indicator_code="B7/JHS1.1.1.1.1",
        learning_focus="Why staying healthy matters",
        curriculum_action_verbs=["explain", "discuss", "research", "present"],
        exemplar_activity_patterns=[
            "Ask learners what they did this morning to take care of their bodies. "
            "List their answers on the board as the beginning of a healthy-day list.",
            "Explain the three sides of staying healthy — physical, mental and "
            "social wellbeing — and link each one to something from the learners' "
            "own morning list.",
            "In groups, learners choose one unhealthy habit (poor rest, unbalanced "
            "diet, drug abuse, negative peer pressure) and prepare a short poster "
            "or illustration showing its consequences, then present to the class.",
        ],
        assessment_patterns=[
            "Ask a learner to name the three sides of staying healthy and give one "
            "example of each.",
            "Check each group's poster states a specific consequence, not a general "
            "warning.",
        ],
        assignment_patterns=[
            "Research and list four materials or habits used to keep the body "
            "healthy, and say how each one helps.",
            "Track one healthy habit for three days and write what you did and how "
            "you felt.",
        ],
        class_assignment_pattern=(
            "Groups choose one unhealthy habit, produce a poster or illustration "
            "showing its consequences, and present it. The teacher checks each "
            "presentation names a specific consequence and one way to avoid it."
        ),
        home_assignment_pattern=(
            "Research and write about two materials or habits used to improve "
            "personal hygiene at home, explaining how each one helps."
        ),
        suitable_resource_patterns=[
            "chart paper and markers for group posters",
            "pictures or illustrations of healthy and unhealthy habits",
            "soap, toothbrush and other hygiene materials where available",
        ],
        focus_terms=[
            "personal hygiene", "physical wellbeing", "mental wellbeing",
            "social wellbeing", "balanced diet", "drug abuse", "peer pressure",
        ],
        core_competencies=[
            "Communication and Collaboration",
            "Personal Development and Leadership",
            "Creativity and Innovation",
        ],
        provenance=(
            "Derived by SchemeKnit from the official NaCCA Career Technology CCP "
            "exemplars for B7/JHS1.1.1.1.1 (explain what staying healthy means — "
            "physical, mental and social wellbeing; discuss and present the "
            "consequences of poor self-care; research materials and strategies for "
            "improving personal hygiene)."
        ),
        **_SOURCE,
    ),
]

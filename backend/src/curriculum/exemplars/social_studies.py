"""
Social Studies — derived exemplar records (NaCCA CCP, Basic 7).

Derived from the official *Social Studies Curriculum for B7/JHS1 – B9/JHS3*,
Common Core Programme (CCP), NaCCA / Ministry of Education, Ghana — Strand 1
(Environment), Sub-strand 1 (Environmental Issues). Derived information only;
no official text is stored.
"""

from __future__ import annotations

from typing import List

from . import ExemplarRecord

_SOURCE = dict(
    source_title=(
        "Social Studies Curriculum for B7/JHS1 – B9/JHS3, Common Core Programme "
        "(CCP), NaCCA / Ministry of Education, Ghana"
    ),
    source_url="https://nacca.gov.gh/wp-content/uploads/2026/09/Social-Studies.pdf",
    source_version="NaCCA/Ministry of Education 2021 (CCP, B7/JHS1 – B9/JHS3)",
)

RECORDS: List[ExemplarRecord] = [
    ExemplarRecord(
        subject="Social Studies",
        level="B7",
        strand="Environment",
        sub_strand="Environmental Issues",
        content_standard_code="B7/JHS1.1.1.1",
        indicator_code="B7/JHS1.1.1.1.1",
        learning_focus="Ways of dealing with sanitation challenges in the environment",
        curriculum_action_verbs=["explain", "discuss", "identify", "examine"],
        exemplar_activity_patterns=[
            "Write the two words ENVIRONMENT and SANITATION on the board and ask "
            "learners to say what each one means. Record their ideas and then give "
            "the class the agreed definition of each word.",
            "Show pictures of a clean compound, a choked gutter and a dumping site. "
            "Ask learners to sort the pictures into physical and social environment "
            "and to name the environmental problem shown in each.",
            "In groups, learners list sanitation problems they can see around their "
            "own community — open defecation, choked drains, refuse heaps, dirty "
            "washrooms. Each group reads its list and the class groups the problems.",
            "Ask learners to talk about one cultural practice in their community "
            "that affects sanitation (for example how waste is handled at funerals "
            "or festivals) and to say what problem it creates.",
            "Lead a discussion on the effects of poor sanitation — sickness, bad "
            "smell, blocked drains, contaminated water — and record the effects in "
            "two columns: effect on people, effect on the environment.",
            "In groups, learners identify ways of managing sanitation problems in "
            "the community and present them to the class as a short list of actions.",
        ],
        assessment_patterns=[
            "Ask each group to state one sanitation problem in their community and "
            "one effect it has. Listen for a named problem and a real consequence.",
            "Ask individual learners to explain the difference between the physical "
            "and the social environment, using an example of each.",
        ],
        assignment_patterns=[
            "Name four sanitation problems in your community and one effect of each.",
            "Explain what is meant by environment and state the two types of "
            "environment with one example each.",
        ],
        class_assignment_pattern=(
            "In groups, learners prepare a short list of the sanitation problems in "
            "their own community and the effect of each problem, then present it to "
            "the class. The teacher checks that each problem named is a real "
            "community problem and that the effect is correctly matched to it."
        ),
        home_assignment_pattern=(
            "Walk around your home and school and record the sanitation problems you "
            "find. For each one, write what causes it and one action the community "
            "could take to manage it."
        ),
        suitable_resource_patterns=[
            "pictures of a clean compound, choked gutters and refuse dumps",
            "chart showing the physical and the social environment",
            "community map or sketch of the school surroundings",
            "video clip on sanitation in the community",
        ],
        focus_terms=[
            "environment", "sanitation", "physical environment",
            "social environment", "sanitation challenges", "open defecation",
            "drainage", "refuse disposal",
        ],
        core_competencies=[
            "Critical Thinking and Problem Solving",
            "Communication and Collaboration",
            "Creativity and Innovation",
        ],
        provenance=(
            "Derived by SchemeKnit from the official NaCCA Social Studies CCP "
            "exemplars for B7/JHS1.1.1.1.1 (explain environment and sanitation; "
            "discuss the physical and social environment; identify environmental "
            "problems including poor sanitation; examine cultural practices and "
            "their sanitation problems; discuss the effects of poor sanitation; "
            "identify ways of managing sanitation problems)."
        ),
        **_SOURCE,
    ),
    ExemplarRecord(
        subject="Social Studies",
        level="B7",
        strand="Environment",
        sub_strand="Environmental Issues",
        content_standard_code="B7/JHS1.1.1.2",
        indicator_code="B7/JHS1 1.1.2.1",
        learning_focus="Sources of energy in Ghana and conserving energy",
        curriculum_action_verbs=["explain", "describe", "categorise", "examine"],
        exemplar_activity_patterns=[
            "Ask learners to name the things in their homes that use energy — the "
            "cooker, the lamp, the torch, the iron. Record the answers and let the "
            "class agree on what energy is.",
            "Show pictures or a short video of fuel wood, a hydro dam, a solar panel "
            "and a thermal plant. Ask learners to describe how each one gives "
            "energy and to say which ones they have seen in Ghana.",
            "Give groups a set of energy source cards. Ask them to sort the cards "
            "into renewable and non-renewable sources and to explain why they put "
            "each card where they did.",
            "Ask learners to examine the benefits of renewable energy and then the "
            "benefits of non-renewable energy, recording the two lists side by side.",
            "In groups, learners design a poster showing how different sources of "
            "energy are used in Ghana and display it for the class to read.",
        ],
        assessment_patterns=[
            "Ask learners to name two renewable and two non-renewable sources of "
            "energy and to give one reason for each classification.",
            "Ask a learner to state one benefit of renewable energy that the class "
            "has not yet mentioned.",
        ],
        assignment_patterns=[
            "List four sources of energy in Ghana and state whether each one is "
            "renewable or non-renewable.",
            "Explain two benefits of using renewable energy in Ghana.",
        ],
        class_assignment_pattern=(
            "Give each group a set of pictures of energy sources. Learners sort them "
            "into renewable and non-renewable and write one benefit of each source. "
            "The teacher checks the classification and the reasons the group gives."
        ),
        home_assignment_pattern=(
            "Find out from an adult at home which source of energy is used for "
            "cooking, lighting and ironing. Record the sources and write one way "
            "each source can be conserved."
        ),
        suitable_resource_patterns=[
            "pictures or videos of fuel wood, hydro, solar and thermal energy",
            "energy source picture cards for sorting",
            "chart showing renewable and non-renewable sources of energy",
            "poster paper and markers for group posters",
        ],
        focus_terms=[
            "energy", "renewable energy", "non-renewable energy", "fuel wood",
            "hydro energy", "solar energy", "thermal energy", "conservation",
        ],
        core_competencies=[
            "Critical Thinking and Problem Solving",
            "Communication and Collaboration",
            "Personal Development and Leadership",
            "Digital Literacy",
        ],
        provenance=(
            "Derived by SchemeKnit from the official NaCCA Social Studies CCP "
            "exemplars for B7/JHS1 1.1.2.1 (explain energy; describe the sources of "
            "energy in Ghana including fuel wood, hydro, solar and thermal; "
            "categorise energy sources into renewable and non-renewable; examine "
            "the benefits of renewable and non-renewable energy; design posters "
            "showing how different sources of energy are used)."
        ),
        **_SOURCE,
    ),
]

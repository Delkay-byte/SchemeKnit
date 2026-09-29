"""
Physical Education and Health — derived exemplar records (NaCCA CCP, Basic 7).

Derived from the official *Physical Education and Health Common Core Programme
(CCP)* curriculum, NaCCA / Ministry of Education, 2021 — Strand 1 (Health
Education), Sub-strand 1 (Nutrition and Physical Activity). Derived only.
"""

from __future__ import annotations

from typing import List

from . import ExemplarRecord

_SOURCE = dict(
    source_title=(
        "Physical Education and Health Curriculum for Basic 7–10, Common Core "
        "Programme (CCP), NaCCA / Ministry of Education, Ghana"
    ),
    source_url=(
        "https://nacca.gov.gh/wp-content/uploads/2023/06/"
        "PHYSICAL-EDUCATION-AND-HEALTH.pdf"
    ),
    source_version="NaCCA/Ministry of Education 2021 (CCP, Basic 7–10)",
)

RECORDS: List[ExemplarRecord] = [
    ExemplarRecord(
        subject="Physical Education and Health",
        level="B7",
        strand="Health Education",
        sub_strand="Nutrition and Physical Activity",
        content_standard_code="B7.1.1.1",
        indicator_code="B7.1.1.1.1",
        learning_focus="Food nutrients needed for physical activity",
        curriculum_action_verbs=["research", "list", "discuss", "explain"],
        exemplar_activity_patterns=[
            "Ask learners what they ate before coming to school and how they felt "
            "during the first break. Record the foods and the feelings on the board.",
            "Group the foods learners named into the three nutrient jobs — energy "
            "foods (carbohydrates: cassava, yam, rice), body-building foods "
            "(proteins: meat, fish, egg) and repair foods (vitamins: fruit, "
            "vegetables) — naming each group as it is formed.",
            "In groups, learners match a set of local food pictures to the nutrient "
            "job each one does, then think-pair-share their list of functions with "
            "another group using the sentence frame 'This food gives ...'.",
        ],
        assessment_patterns=[
            "Ask each group to name one energy food, one body-building food and one "
            "repair food, giving the nutrient for each.",
            "Listen for the function of the nutrient, not only the food name.",
        ],
        assignment_patterns=[
            "Record everything you eat for one day and label each food with the "
            "nutrient it supplies.",
            "Write what happens to a learner who eats only energy foods before a "
            "games lesson and explain why.",
        ],
        class_assignment_pattern=(
            "Groups match local food pictures to the nutrient job each performs and "
            "report using the frame 'This food gives ...'. The teacher checks each "
            "group names both the food and its nutrient function."
        ),
        home_assignment_pattern=(
            "Ask at home for the foods usually eaten before and after sport. List "
            "them and write the nutrient each one supplies and why the body needs "
            "it for physical activity."
        ),
        suitable_resource_patterns=[
            "pictures or drawings of local foods",
            "chart headed with the three nutrient jobs",
            "real food items where available",
        ],
        focus_terms=[
            "food nutrients", "carbohydrates", "proteins", "vitamins",
            "energy foods", "body-building foods", "physical activity",
        ],
        core_competencies=[
            "Critical Thinking and Problem Solving",
            "Communication and Collaboration",
            "Personal Development and Leadership",
        ],
        provenance=(
            "Derived by SchemeKnit from the official NaCCA Physical Education and "
            "Health CCP exemplars for B7.1.1.1.1 (research and list food nutrients "
            "— energy-supplying, body-building and repair foods; discuss their "
            "functions in physical activity and share findings with other groups)."
        ),
        **_SOURCE,
    ),
]

"""Priority 2.1 — deterministic lesson-authoring HARDENING benchmark.

Frozen BEFORE the hardening edits: the corpora below are the fixture set the
hardening pass is measured against, so the numbers cannot be tuned after the
fact.

Two corpora, ONE rubric (imported unchanged from
``benchmark_deterministic_lessons`` — no criterion, threshold or weight is
redefined here):

``CORPUS``
    The EXPANDED benchmark: 39 real curriculum occurrences across 12 subjects
    (Mathematics, Science, English, Computing, Creative Arts, Social Studies,
    Religious and Moral Education, PHE, Career Technology, Ghanaian Language,
    French, History). Indicator texts are repository fixtures, official-corpus
    learning focuses, or rows taken verbatim from the real Ghanaian scheme
    documents in ``backend/real_documents/``.

``MESSY_CORPUS``
    The MESSY-SOURCE benchmark: rows copied VERBATIM from
    ``real_documents/BASIC 6 TERM 1.docx`` — inline codes, " : " and " . "
    separators, two sentences merged into one indicator cell, duplicated
    indicator rows across weeks, multi-indicator weeks, accented French text
    and scheme resources a real classroom cannot be expected to have.

Usage (from backend/):
    ./venv/Scripts/python tests/benchmark_hardening.py --out ../docs/benchmark/hardening_after.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import benchmark_deterministic_lessons as base  # noqa: E402  (single rubric)

from src.models import (  # noqa: E402
    AIMode,
    ClassLevel,
    SchemeOfWork,
    Subject,
    TermConfig,
    Week,
    WeekType,
)

B7 = ClassLevel.BASIC_7
B6 = ClassLevel.BASIC_6

#: Marker coverage for the subjects the hardening benchmark adds. This only
#: teaches the SHARED rubric which vocabulary belongs to which subject — no
#: criterion, threshold or weight changes (c13 still needs >= 5 distinct
#: markers for a 5, exactly as before).
_MARKERS_TO_ADD = {
    "phe": r"\b(warm[- ]?up|safety|fitness|technique|drill|game|ball|"
           r"posture|exercise|pace|team|movement|skill)\b",
    "career": r"\b(material|materials|tool|tools|procedure|product|"
              r"measure|assemble|safety|process|design|quality|cost)\b",
}
for _k, _pat in _MARKERS_TO_ADD.items():
    base._SUBJECT_MARKERS.setdefault(_k, re.compile(_pat, re.I))

# Subject enum → the marker vocabulary c13 scores against.
base.SUBJECT_STRAND_KEY.update({
    Subject.RME: "rme",
    Subject.PHE: "phe",
    Subject.CAREER_TECHNOLOGY: "career",
    Subject.FRENCH: "english",
    Subject.GHANAIAN_LANGUAGE: "english",
    Subject.HISTORY: "social studies",
})


def E(subject, cls, week, code, indicator, strand, sub_strand, cs_code,
      content_standard, resources, provenance, group=""):
    """One frozen corpus entry (``group`` = shares a source week row)."""
    return dict(
        subject=subject, class_level=cls, week=week, code=code,
        indicator=indicator, strand=strand, sub_strand=sub_strand,
        content_standard_code=cs_code, content_standard=content_standard,
        resources=list(resources), provenance=provenance, group=group,
    )


# ── EXPANDED corpus: 39 occurrences, 12 subjects ────────────────────────────

CORPUS = [
    # 1–11 — the established 11-lesson benchmark, unchanged.
    E(Subject.MATHEMATICS, B7, 1, "B7.1.1.1.1",
      "Use place value to read and write numbers",
      "Number", "Number and Numeration Systems", "B7.1.1.1",
      "Demonstrate understanding of place value of digits in whole numbers",
      ["multi-base blocks", "place value chart", "exercise books"],
      "NaCCA B7 indicator used in tests/test_curriculum_v2.py; exemplar record B7.1.1.1.1"),
    E(Subject.MATHEMATICS, B7, 2, "B7.1.1.1.1",
      "Use place value to read and write numbers",
      "Number", "Number and Numeration Systems", "B7.1.1.1",
      "Demonstrate understanding of place value of digits in whole numbers",
      ["multi-base blocks", "place value chart", "exercise books"],
      "REPEAT of week 1 occurrence (progression probe)"),
    E(Subject.MATHEMATICS, B7, 3, "B7.1.1.1.3",
      "Solve word problems involving addition and subtraction",
      "Number", "Number and Numeration Systems", "B7.1.1.1",
      "Apply number operations to solve everyday problems",
      ["exercise books", "chalkboard", "word problem cards"],
      "SchemeKnit fixture occurrence (tests/test_generation_quality_v3.py MATH_CODES)"),
    E(Subject.SCIENCE, B7, 1, "B7.1.1.1.1",
      "Classify materials as solids, liquids and gases",
      "Matter", "Classification of Materials", "B7.1.1.1",
      "Demonstrate understanding of the states of matter",
      ["local samples (water, sand, stone)", "containers", "recording sheets"],
      "Exemplar record B7/JHS1.1.1.1.1 (src/curriculum/exemplars/science.py)"),
    E(Subject.SCIENCE, B7, 2, "B7.2.1.1.1",
      "Describe the characteristics of living things",
      "Diversity of Life", "Living Things", "B7.2.1.1",
      "Demonstrate understanding of characteristics of living things",
      ["leaf samples", "chalkboard", "exercise books"],
      "SchemeKnit fixture occurrence (tests/test_generation_quality_v3.py SCI_CODES)"),
    E(Subject.ENGLISH, B7, 1, "B7.1.1.1.1",
      "Use formal and informal register in conversation",
      "Communication", "Speaking and Listening", "B7.1.1.1",
      "Demonstrate the ability to communicate appropriately in different situations",
      ["conversation cards", "chalkboard", "exercise books"],
      "Exemplar record B7/JHS1.1.1.1.1 (src/curriculum/exemplars/english.py)"),
    E(Subject.ENGLISH, B7, 2, "B7.1.1.1.2",
      "Ask questions to elicit elaboration in conversation",
      "Communication", "Speaking and Listening", "B7.1.1.1",
      "Demonstrate the ability to communicate appropriately in different situations",
      ["question cards", "chalkboard", "exercise books"],
      "Exemplar record B7/JHS1.1.1.1.2 (src/curriculum/exemplars/english.py)"),
    E(Subject.ICT, B7, 1, "B7.1.1.1.2",
      "Distinguish between manual and automatic devices",
      "Introduction to Computing", "Components of Computers and Computer Systems",
      "B7.1.1.1", "Demonstrate understanding of computer systems and their components",
      ["sample input devices (keyboard, mouse, scanner)", "chart", "exercise books"],
      "Fixture occurrence (tests/test_lesson_quality_remediation.py) + exemplar record B7.1.1.1.2"),
    E(Subject.ICT, B7, 2, "B7.1.1.2.1",
      "Demonstrate how to use the Start screen, tiles and taskbar",
      "Introduction to Computing", "Windows and the Desktop", "B7.1.1.2",
      "Demonstrate understanding of the operating system and its interface",
      ["computer or projected screen where available", "unplugged keyboard diagram",
       "exercise books"],
      "Derived from exemplar record B7.1.1.2.1 learning focus + curriculum action verbs"),
    E(Subject.CREATIVE_ARTS, B7, 1, "B7.5.1.1.1",
      "Create a simple pattern using local materials",
      "Design", "Pattern and Decoration", "B7.5.1.1",
      "Demonstrate ability to create designs and works using local materials",
      ["local materials (seeds, leaves, cloth scraps)", "manila paper", "glue"],
      "SchemeKnit fixture occurrence (tests/test_generation_quality_v3.py CRE_CODES)"),
    E(Subject.SOCIAL_STUDIES, B7, 1, "B7.1.1.2.1",
      "Explain sources of energy in Ghana and ways of conserving energy",
      "Our Environment", "Energy Resources", "B7.1.1.2",
      "Demonstrate understanding of energy resources and their conservation",
      ["chart of local energy sources", "chalkboard", "exercise books"],
      "Exemplar record B7/JHS1 1.1.2.1 (src/curriculum/exemplars/social_studies.py)"),

    # 12–17 — Mathematics, repository batch fixture (BATCH_INDICATORS).
    E(Subject.MATHEMATICS, B7, 4, "B7.1.1.1.1",
      "Add whole numbers up to 10,000", "Number", "Number and Numeration",
      "B7.1.1.1", "B7.1.1.1 Number",
      ["counters and bundles of sticks", "place-value chart", "number cards",
       "exercise books and pencils"],
      "Repository fixture (tests/test_batch_variation_benchmark.py BATCH_INDICATORS)"),
    E(Subject.MATHEMATICS, B7, 5, "B7.1.1.2.1",
      "Multiply two-digit numbers by two-digit numbers", "Number", "Number and Numeration",
      "B7.1.1.1", "B7.1.1.1 Number",
      ["counters and bundles of sticks", "place-value chart", "number cards",
       "exercise books and pencils"],
      "Repository fixture (tests/test_batch_variation_benchmark.py BATCH_INDICATORS)"),
    E(Subject.MATHEMATICS, B7, 6, "B7.1.2.1.1",
      "Identify prime numbers up to 100", "Number", "Number and Numeration",
      "B7.1.1.1", "B7.1.1.1 Number",
      ["counters and bundles of sticks", "place-value chart", "number cards",
       "exercise books and pencils"],
      "Repository fixture (tests/test_batch_variation_benchmark.py BATCH_INDICATORS)"),
    E(Subject.MATHEMATICS, B7, 7, "B7.1.3.1.1",
      "Compare fractions with the same denominator", "Number", "Number and Numeration",
      "B7.1.1.1", "B7.1.1.1 Number",
      ["counters and bundles of sticks", "place-value chart", "number cards",
       "exercise books and pencils"],
      "Repository fixture (tests/test_batch_variation_benchmark.py BATCH_INDICATORS)"),
    E(Subject.MATHEMATICS, B7, 8, "B7.1.4.1.1",
      "Investigate the properties of 2-D shapes", "Shape and Space", "2-D Shapes",
      "B7.1.4.1", "B7.1.4.1 Investigate properties of 2-D shapes",
      ["cut-out shapes", "chalkboard", "exercise books", "rulers"],
      "Repository fixture (tests/test_batch_variation_benchmark.py BATCH_INDICATORS)"),
    E(Subject.MATHEMATICS, B7, 9, "B7.1.5.1.1",
      "Interpret data presented in a bar chart", "Shape and Space", "Data Handling",
      "B7.1.5.1", "B7.1.5.1 Interpret data presented in a bar chart",
      ["bar chart on the board", "graph sheets", "exercise books"],
      "Repository fixture (tests/test_batch_variation_benchmark.py BATCH_INDICATORS)"),

    # 18–19 — Science, repository batch fixture.
    E(Subject.SCIENCE, B7, 3, "B7.2.1.1.2",
      "Investigate the states of matter", "Matter", "States of Matter",
      "B7.2.1.1", "B7.2.1.1 Investigate the states of matter",
      ["beakers", "water", "ice", "exercise books"],
      "Repository fixture (tests/test_batch_variation_benchmark.py cross-subject batch)"),
    E(Subject.SCIENCE, B7, 4, "B7.2.2.1.1",
      "Classify materials into conductors and insulators", "Energy and Change",
      "Electrical Energy", "B7.2.2.1", "B7.2.2.1 Classify conductors and insulators",
      ["dry cells", "small bulbs", "wires", "objects to test"],
      "Repository fixture (tests/test_batch_variation_benchmark.py cross-subject batch)"),

    # 20–22 — Computing, repository fixtures.
    E(Subject.ICT, B7, 3, "B7.1.1.1",
      "Identify hardware components.",
      "Introduction to Computing", "Components of a Computer System",
      "B7.1.1.1", "B7.1.1.1 Identify hardware components",
      ["chart of computer parts", "exercise books"],
      "Repository fixture (tests/test_final_web_ux.py objective contract)"),
    E(Subject.ICT, B7, 4, "B7.1.1.2",
      "Install an operating system.",
      "Introduction to Computing", "Operating Systems", "B7.1.1.2",
      "B7.1.1.2 Install an operating system",
      ["computer or unplugged steps on the board", "exercise books"],
      "Repository fixture (tests/test_final_web_ux.py objective contract)"),
    E(Subject.ICT, B7, 5, "B7.1.1.2.1",
      "Explain how a computer stores data",
      "Introduction to Computing", "Data Storage", "B7.1.1.2",
      "B7.1.1.2 Explain how a computer stores data",
      ["storage media samples", "chart", "exercise books"],
      "Repository fixture (tests/test_lesson_quality_remediation.py)"),

    # 23–24 — English + Social Studies fixtures.
    E(Subject.ENGLISH, B7, 3, "B7.3.1.1.1",
      "Use adjectives correctly in sentences", "Communication", "Written Language",
      "B7.3.1.1", "B7.3.1.1 Use adjectives correctly in sentences",
      ["sentence cards", "chalkboard", "exercise books"],
      "Repository fixture (tests/test_generation_quality_v3.py ENG_CODES)"),
    E(Subject.SOCIAL_STUDIES, B7, 2, "B7.4.1.1.1",
      "Discuss the roles of members of the family", "The Family", "Family Roles",
      "B7.4.1.1", "B7.4.1.1 Discuss the roles of members of the family",
      ["family pictures", "chalkboard", "exercise books"],
      "Repository fixture (tests/test_generation_quality_v3.py SOC_CODES)"),

    # 25–29 — official-corpus learning focuses (one record each).
    E(Subject.PHE, B7, 1, "B7.1.1.1.1",
      "Food nutrients needed for physical activity",
      "Health Education", "Nutrition and Physical Activity", "B7.1.1.1",
      "B7.1.1.1 Research and discuss the nutrients needed for physical activity",
      ["food charts", "local food samples", "exercise books"],
      "Exemplar record B7.1.1.1.1 (src/curriculum/exemplars/phe.py)"),
    E(Subject.RME, B7, 1, "B7/JHS1 1.1.1.1",
      "Attributes of God in the three major religions",
      "God, His Creation and Attributes", "God, His Nature and Attributes",
      "B7/JHS1 1.1.1", "B7/JHS1 1.1.1 Identify the attributes of God",
      ["source texts", "wall chart", "exercise books"],
      "Exemplar record B7/JHS1 1.1.1.1 (src/curriculum/exemplars/rme.py)"),
    E(Subject.RME, B7, 2, "B7/JHS1 1.1.1.2",
      "Demonstrating the attributes of God in daily life",
      "God, His Creation and Attributes", "God, His Nature and Attributes",
      "B7/JHS1 1.1.1", "B7/JHS1 1.1.1 Demonstrate the attributes of God in daily life",
      ["real-life scenario cards", "chalkboard", "exercise books"],
      "Exemplar record B7/JHS1 1.1.1.2 (src/curriculum/exemplars/rme.py)"),
    E(Subject.CAREER_TECHNOLOGY, B7, 1, "B7/JHS1.1.1.1.1",
      "Why staying healthy matters", "Personal Hygiene and Food Hygiene",
      "Personal Hygiene and Food Hygiene", "B7/JHS1.1.1.1",
      "B7/JHS1.1.1.1 Explain why staying healthy matters",
      ["pictures of local foods", "chart", "exercise books"],
      "Exemplar record B7/JHS1.1.1.1.1 (src/curriculum/exemplars/career_technology.py)"),
    E(Subject.CREATIVE_ARTS, B7, 2, "B7/JHS1 1.1.1.1",
      "Design in nature and the manmade environment", "Design",
      "Design in Nature and Manmade Environment", "B7/JHS1 1.1.1",
      "B7/JHS1 1.1.1 Research and identify designs in nature",
      ["leaves and seeds", "manila paper", "exercise books"],
      "Exemplar record B7/JHS1 1.1.1.1 (src/curriculum/exemplars/creative_arts.py)"),

    # 30–39 — real rows from backend/real_documents/BASIC 6 TERM 1.docx.
    E(Subject.GHANAIAN_LANGUAGE, B6, 1, "B6.1.1.1.1",
      "B6.1.1.1.1 : Sing some traditional songs which are used for traditional dances and their correct rhythms",
      "Oral Language", "Songs", "B6.1.1.1",
      "B6.1.1.1 : Investigate some traditional dances and their songs",
      ["Video clips"],
      "real_documents/BASIC 6 TERM 1.docx — Ghanaian Language week 1 row (verbatim)"),
    E(Subject.GHANAIAN_LANGUAGE, B6, 3, "B6.1.1.1.2",
      "B6.1.1.1.2 : Discuss the importance and some moral lessons of the songs and the dances.",
      "Oral Language", "Songs", "B6.1.1.1",
      "B6.1.1.1 : Investigate some traditional dances and their songs",
      ["Old Magazines", "Word cards", "Video clips", "Sentence cards"],
      "real_documents/BASIC 6 TERM 1.docx — Ghanaian Language week 3 row (verbatim)"),
    E(Subject.GHANAIAN_LANGUAGE, B6, 5, "B6.1.4.1.1",
      "B6.1.4.1.1 : Indicate the similarities and differences between folktales and stories",
      "Oral Language", "Listening and storytelling", "B6.1.4.1",
      "B6.1.4.1 : Demonstrate an understanding and comparison of folktales to stories",
      ["Word cards"],
      "real_documents/BASIC 6 TERM 1.docx — Ghanaian Language week 5 row (verbatim)"),
    E(Subject.FRENCH, B6, 6, "B6.1.3.3.1",
      "B6.1.3.3.1 Lire et comprendre le portrait/biographie d\u2019une personne historique \u00e9crire une carte postale \u00e0 un/une correspondant(e) pour pr\u00e9senter quelqu\u2019un en donnant sa date de naissance, son lieu de naissance, son num\u00e9ro de t\u00e9l\u00e9phone",
      "L\u2019identit\u00e9", "Pr\u00e9senter quelqu\u2019un", "B6.1.3.1",
      "B6.1.3.1 Pr\u00e9senter quelqu\u2019un",
      ["L\u2019ordinateur", "Vid\u00e9o Texte dialogue"],
      "real_documents/BASIC 6 TERM 1.docx — French week 6 row (verbatim, accented source text)"),
    E(Subject.FRENCH, B6, 8, "B6.1.4.3.1",
      "B6.1.4.3.1 Lire et comprendre des textes simples sur les caract\u00e9ristiques physiques, l\u2019habillement et les comportements d\u2019une personne D\u00e9crire quelqu\u2019un en indiquant ses caract\u00e9ristiques physiques, l\u2019habillement et les comportements",
      "L\u2019identit\u00e9", "D\u00e9crire quelqu\u2019un", "B6.1.4.1",
      "B6.1.4.1 (D\u00e9crire quelqu\u2019un)",
      ["L\u2019ordinateur", "Projecteur", "Le corps humain"],
      "real_documents/BASIC 6 TERM 1.docx — French week 8 row (verbatim, accented source text)"),
    E(Subject.HISTORY, B6, 1, "B6.3.4.1.1",
      "B6.3.4.1.1 Assess the changes that the European presence brought to Ghana",
      "Europeans in Ghana", "Impact of European presence", "B6.3.4.1",
      "B6.3.4.1 Demonstrates knowledge of the impact of European presence on Ghana",
      ["A map of Ghana posters documentary"],
      "real_documents/BASIC 6 TERM 1.docx — History week 1 row (verbatim)"),
    E(Subject.RME, B6, 5, "B6.1.2.1.2",
      "B6.1.2.1.2 . Explain the Religious and moral lessons in preserving the environment",
      "God, His Creation and Attributes", "The Environment", "B6.1.2.1",
      "B6.1.2.1 . Appreciates the uniqueness of humankind and their environments",
      ["Posters"],
      "real_documents/BASIC 6 TERM 1.docx — RME week 5 row (verbatim, ' . ' code separator)"),
    E(Subject.MATHEMATICS, B6, 10, "B6.1.1.3.1",
      "B6.1.1.3.1 : Determine the HCF and the LCM of two or three numbers using prime factors",
      "Number", "Counting, Representation, Cardinality, and Ordinality", "B6.1.1.3",
      "B6.1.1.3 : Demonstrate factors, multiples, and prime numbers from 1 to 100",
      ["Counters"],
      "real_documents/BASIC 6 TERM 1.docx — Mathematics week 7 row (verbatim)"),
    E(Subject.SCIENCE, B6, 5, "B6.2.1.4.1",
      "B6.2.1.4.1 Investigate ways of conserving water in the home, school and community",
      "Cycles", "Earth Science", "B6.2.1.4",
      "B6.2.1.4 Recognise water and air as important natural resources",
      ["Charcoal", "coal pot", "filter", "container with lid", "alum", "water", "matches"],
      "real_documents/BASIC 6 TERM 1.docx — Science week 5 row (verbatim)"),
    E(Subject.ICT, B6, 4, "B6.1.1.1.1",
      "B6.1.1.1.1 . Learn about the generations of computers",
      "Introduction to Computing",
      "Generation of Computers and Parts of a Computer and Other Gadgets",
      "B6.1.1.1", "B6.1.1.1 : Identify parts of a computer, technology tools, and history of computers",
      ["Pictures of the generations of computers"],
      "real_documents/BASIC 6 TERM 1.docx — ICT week 1 row (verbatim)"),
    E(Subject.ENGLISH, B6, 7, "B6.1.3.1.1",
      "B6.1.3.1.1 : Relate the central messages of poems to personal experiences.",
      "Oral Language", "Poem", "B6.1.3.1",
      "B6.1.3.1 : Appreciate poems and other pieces of literary materials",
      ["Word cards", "Flash Cards"],
      "real_documents/BASIC 6 TERM 1.docx — English Language week 4 row (verbatim)"),
]


# ── MESSY-SOURCE corpus: verbatim rows from a real scheme ───────────────────
#
# Every indicator string below is character-for-character what the DOCX parser
# reads out of backend/real_documents/BASIC 6 TERM 1.docx for that subject and
# week (codes, separators, merged sentences and accents included). Entries that
# share a ``group`` came from ONE source week, so the benchmark keeps the real
# multi-indicator week structure.

MESSY_CORPUS = [
    # French — accented source text, two indicators that repeat one sentence.
    E(Subject.FRENCH, B6, 1, "B6.1.1.1.1",
      "B6.1.1.1.1 \u00c9couter/Regarder et comprendre un document audiovisuel dans lequel deux personnes se saluent Saluer et r\u00e9pondre oralement aux salutations et respecter le code et les valeurs sociales",
      "L\u2019identit\u00e9", "Saluer et prendre cong\u00e9.", "B6.1.1.1",
      "B6.1.1.1 (Saluer et prendre cong\u00e9)",
      ["audio", "Vid\u00e9o", "haut-parleur d\u2019ordinateur"],
      "real_documents/BASIC 6 TERM 1.docx — French week 1 row (verbatim)",
      group="fr-w1"),
    E(Subject.FRENCH, B6, 1, "B6.1.1.2.1",
      "B6.1.1.2.1 \u00c9couter/Regarder et comprendre un document audiovisuel dans lequel deux personnes se saluent Saluer et r\u00e9pondre oralement aux salutations et respecter le code et les valeurs sociales",
      "L\u2019identit\u00e9", "Saluer et prendre cong\u00e9.", "B6.1.1.1",
      "B6.1.1.1 (Saluer et prendre cong\u00e9)",
      ["audio", "Vid\u00e9o", "haut-parleur d\u2019ordinateur"],
      "real_documents/BASIC 6 TERM 1.docx — French week 1 row (verbatim, duplicate sentence)",
      group="fr-w1"),

    # Creative Arts — two sentences merged into one indicator cell by " : ",
    # and the scheme itself asks for internet resources.
    E(Subject.CREATIVE_ARTS, B6, 4, "B6.1.1.1.3",
      "B6.1.1.1.3 : Study some artworks created by international visual artists that reflect the physical and social environments of some communities in the world. : Generate own ideas for designing and creating own visual artworks based on the physical and social environments of some communities in the world.",
      "Visual Arts", "Thinking and Exploring Ideas", "B6.1.1.1",
      "B6.1.1.1 : Demonstrate understanding of how to generate own ideas for artistic expressions on the people based on their history and culture, the environment and topical local, national/global issues.",
      ["drawing paper and pencils", "internet resources",
       "Pictures/videos of physical and social environments",
       "samples of international visual artworks"],
      "real_documents/BASIC 6 TERM 1.docx — Creative Arts week 4 row (verbatim, merged sentences + impossible resource)",
      group="cad-w4"),
    E(Subject.CREATIVE_ARTS, B6, 4, "B6.1.1.1.4",
      "B6.1.1.1.4 : Study some artworks created by international visual artists that reflect the physical and social environments of some communities in the world. : Generate own ideas for designing and creating own visual artworks based on the physical and social environments of some communities in the world.",
      "Visual Arts", "Thinking and Exploring Ideas", "B6.1.1.1",
      "B6.1.1.1 : Demonstrate understanding of how to generate own ideas for artistic expressions on the people based on their history and culture, the environment and topical local, national/global issues.",
      ["drawing paper and pencils", "internet resources",
       "Pictures/videos of physical and social environments",
       "samples of international visual artworks"],
      "real_documents/BASIC 6 TERM 1.docx — Creative Arts week 4 row (verbatim, merged sentences)",
      group="cad-w4"),

    # ICT — " . " joined sentences in the indicator cell.
    E(Subject.ICT, B6, 3, "B6.1.1.1.4",
      "B6.1.1.1.4 . Demonstrate proper use of keyboarding techniques. . Summarise the generations of computers (second generation of computers)",
      "Introduction to Computing",
      "Generation of Computers and Parts of a Computer and Other Gadgets",
      "B6.1.1.1", "B6.1.1.1 : Identify parts of a computer, technology tools and history of computers",
      ["Computer"],
      "real_documents/BASIC 6 TERM 1.docx — ICT week 3 row (verbatim, ' . ' joined sentences)",
      group="ict-w3"),
    E(Subject.ICT, B6, 3, "B6.1.1.1.5",
      "B6.1.1.1.5 . Demonstrate proper use of keyboarding techniques. . Summarise the generations of computers (second generation of computers)",
      "Introduction to Computing",
      "Generation of Computers and Parts of a Computer and Other Gadgets",
      "B6.1.1.1", "B6.1.1.1 : Identify parts of a computer, technology tools and history of computers",
      ["Computer"],
      "real_documents/BASIC 6 TERM 1.docx — ICT week 3 row (verbatim, ' . ' joined sentences)",
      group="ict-w3"),

    # English — six indicator cells in one week, list junk inside a cell.
    E(Subject.ENGLISH, B6, 4, "B6.1.3.1.1",
      "B6.1.3.1.1 : Relate the central messages of poems to personal experiences.",
      "Oral Language", "Poem", "B6.1.3.1",
      "B6.1.3.1 : Appreciate poems and other pieces of literary materials",
      ["Word cards", "Flash Cards"],
      "real_documents/BASIC 6 TERM 1.docx — English Language week 4 row (verbatim)",
      group="eng-w4"),
    E(Subject.ENGLISH, B6, 4, "B6.3.1.1.2",
      "B6.3.1.1.2 : Identify and use: - Proper noun - Count / non \u2013 count - Singular \u2013 Plural (regular, irregular) - Without plural marker.",
      "Oral Language", "Poem", "B6.3.1.1",
      "B6.3.1.1 : Apply knowledge of different types of nouns in communication",
      ["Word cards", "Flash Cards"],
      "real_documents/BASIC 6 TERM 1.docx — English Language week 4 row (verbatim, list junk)",
      group="eng-w4"),
    E(Subject.ENGLISH, B6, 4, "B6.6.1.1.1",
      "B6.6.1.1.1 : Read and critique a variety of age \u2013 and level appropriate books and present one. page critical commentary based on a set of criteria, on each book read.",
      "Oral Language", "Poem", "B6.6.1.1",
      "B6.6.1.1 : Read widely for pleasure, to demonstrate independent reading and learning in the literary / content areas.",
      ["Word cards", "Flash Cards"],
      "real_documents/BASIC 6 TERM 1.docx — English Language week 4 row (verbatim, split word)",
      group="eng-w4"),

    # Ghanaian Language — four indicators and four content standards in one week.
    E(Subject.GHANAIAN_LANGUAGE, B6, 2, "B6.2.4.1.1",
      "B6.2.4.1.1 : Read and recognise words with digraphs in sentences and paragraphs",
      "Reading", "Phonics", "B6.2.4.1",
      "B6.2.4.1 : Demonstrate ability to listen and pronounce words with identical sounds from a list of words",
      ["Letter cards", "Magazines", "Word cards", "Sentence cards"],
      "real_documents/BASIC 6 TERM 1.docx — Ghanaian Language week 2 row (verbatim)",
      group="gl-w2"),
    E(Subject.GHANAIAN_LANGUAGE, B6, 2, "B6.3.1.1.1",
      "B6.3.1.1.1 : Pay attention to ascending and descending letters that are not easy to write",
      "Reading", "Phonics", "B6.3.1.1",
      "B6.3.1.1 : Write sentences clearly and correctly, using correct capitalization where needed",
      ["Letter cards", "Magazines", "Word cards", "Sentence cards"],
      "real_documents/BASIC 6 TERM 1.docx — Ghanaian Language week 2 row (verbatim)",
      group="gl-w2"),
    E(Subject.GHANAIAN_LANGUAGE, B6, 2, "B6.5.1.1.1",
      "B6.5.1.1.1 : Use the upper case letters after colons and question marks",
      "Reading", "Phonics", "B6.5.1.1",
      "B6.5.1.1 : Exhibit knowledge of using capital letters appropriately",
      ["Letter cards", "Magazines", "Word cards", "Sentence cards"],
      "real_documents/BASIC 6 TERM 1.docx — Ghanaian Language week 2 row (verbatim)",
      group="gl-w2"),
    E(Subject.GHANAIAN_LANGUAGE, B6, 2, "B6.6.1.1.1",
      "B6.6.1.1.1 : Recognise topics for magazine",
      "Reading", "Phonics", "B6.6.1.1",
      "B6.6.1.1 : Exhibit knowledge of understanding and appreciating magazines",
      ["Letter cards", "Magazines", "Word cards", "Sentence cards"],
      "real_documents/BASIC 6 TERM 1.docx — Ghanaian Language week 2 row (verbatim)",
      group="gl-w2"),

    # Mathematics — " : " separators, two indicators in one week.
    E(Subject.MATHEMATICS, B6, 5, "B6.1.1.1.5",
      "B6.1.1.1.5 : Round (off, up, down) whole numbers up to 100,000 to the nearest ten thousand, thousands, hundreds, and tens.",
      "Number", "Counting, Representation, Cardinality, and Ordinality", "B6.1.1.1",
      "B6.1.1.1 : Demonstrate an understanding of quantities and place value for multi-digit numerals up to 1,000,000,000 or 1 billion",
      ["Number chart"],
      "real_documents/BASIC 6 TERM 1.docx — Mathematics week 5 row (verbatim)",
      group="math-w5"),
    E(Subject.MATHEMATICS, B6, 5, "B6.1.1.1.6",
      "B6.1.1.1.6 : Skip count forwards and backwards in 5,000s, 10,000s, etc. up to and from 1,000,000.",
      "Number", "Counting, Representation, Cardinality, and Ordinality", "B6.1.1.1",
      "B6.1.1.1 : Demonstrate an understanding of quantities and place value for multi-digit numerals up to 1,000,000,000 or 1 billion",
      ["Number chart"],
      "real_documents/BASIC 6 TERM 1.docx — Mathematics week 5 row (verbatim)",
      group="math-w5"),

    # History — the SAME indicator repeated in a later week (real progression).
    E(Subject.HISTORY, B6, 1, "B6.3.4.1.1",
      "B6.3.4.1.1 Assess the changes that the European presence brought to Ghana",
      "Europeans in Ghana", "Impact of European presence", "B6.3.4.1",
      "B6.3.4.1 Demonstrates knowledge of the impact of European presence on Ghana",
      ["A map of Ghana posters documentary"],
      "real_documents/BASIC 6 TERM 1.docx — History week 1 row (verbatim)"),
    E(Subject.HISTORY, B6, 4, "B6.3.4.1.1",
      "B6.3.4.1.1 Assess the changes that the European presence brought to Ghana",
      "Europeans in Ghana", "Impact of European presence", "B6.3.4.1",
      "B6.3.4.1 Demonstrates knowledge of the impact of European presence on Ghana",
      ["A map of Ghana posters documentary"],
      "real_documents/BASIC 6 TERM 1.docx — History week 4 row (verbatim, repeat of week 1)"),

    # RME — code and text separated by " . ".
    E(Subject.RME, B6, 5, "B6.1.2.1.2",
      "B6.1.2.1.2 . Explain the Religious and moral lessons in preserving the environment",
      "God, His Creation and Attributes", "The Environment", "B6.1.2.1",
      "B6.1.2.1 . Appreciates the uniqueness of humankind and their environments",
      ["Posters"],
      "real_documents/BASIC 6 TERM 1.docx — RME week 5 row (verbatim, ' . ' code separator)"),

    # Science — scheme resources a real classroom actually has.
    E(Subject.SCIENCE, B6, 5, "B6.2.1.4.1",
      "B6.2.1.4.1 Investigate ways of conserving water in the home, school and community",
      "Cycles", "Earth Science", "B6.2.1.4",
      "B6.2.1.4 Recognise water and air as important natural resources",
      ["Charcoal", "coal pot", "filter", "container with lid", "alum", "water", "matches"],
      "real_documents/BASIC 6 TERM 1.docx — Science week 5 row (verbatim)"),
]


# ── Scheme / config construction ────────────────────────────────────────────


def build_scheme(entries):
    """One SchemeOfWork per (subject, class level); source weeks kept intact.

    Entries that share a ``group`` stay in ONE week (the real multi-indicator
    row), so allocation sees exactly the structure the document had.
    """
    buckets = []
    for entry in entries:
        key = (entry["subject"], entry["class_level"])
        for bucket in buckets:
            if bucket["key"] == key:
                bucket["entries"].append(entry)
                break
        else:
            buckets.append({"key": key, "entries": [entry]})

    schemes = []
    for bucket in buckets:
        entries_b = bucket["entries"]
        weeks = []
        groups = []
        for entry in entries_b:
            gkey = entry.get("group") or f"__solo_{len(groups)}"
            for group in groups:
                if group["key"] == gkey:
                    group["entries"].append(entry)
                    break
            else:
                groups.append({"key": gkey, "entries": [entry]})
        for index, group in enumerate(groups, start=1):
            head = group["entries"][0]
            # Fixture rows carry the indicator text only; real DOCX rows carry
            # "B6.1.1.1.1 …" already, so never prefix those twice.
            indicators = [
                e["indicator"] if e["indicator"].lstrip().startswith(e["code"])
                else f'{e["code"]} {e["indicator"]}'
                for e in group["entries"]
            ]
            weeks.append(Week(
                week_number=index,
                start_date=date(2026, 9, 7) + timedelta(days=7 * (index - 1)),
                end_date=date(2026, 9, 11) + timedelta(days=7 * (index - 1)),
                week_type=WeekType.INSTRUCTION,
                strand=head["strand"], sub_strand=head["sub_strand"],
                content_standards=[head["content_standard"]],
                indicators=indicators,
                resources=list(head["resources"]),
                scheme_of_work_id="hardening-bench",
            ))
        subject, class_level = bucket["key"]
        schemes.append(SchemeOfWork(
            id="hardening-bench", filename="hardening_benchmark.docx",
            class_level=class_level, subject=subject,
            term="First Term", academic_year="2026/2027",
            weeks=weeks, upload_date=date(2026, 9, 1),
        ))
    return schemes


def build_config(subject, class_level, duration):
    return TermConfig(
        scheme_of_work_id="hardening-bench", academic_year="2026/2027",
        term="First Term", class_level=class_level, subject=subject,
        term_start_date=date(2026, 9, 7), term_end_date=date(2026, 12, 18),
        lessons_per_week=1, lesson_duration_minutes=duration,
        teaching_days=[0], holidays=[], ai_mode=AIMode.OFF,
        school_name="Benchmark School", teacher_name="Benchmark Teacher",
    )


def run_generation(corpus):
    """Generate every lesson on the real pipeline (AI OFF, Zeli OFF).

    Returns ``(entry, lesson)`` pairs in corpus order.
    """
    from src.engines.generation_pipeline import GenerationPipeline

    schemes = build_scheme(corpus)
    results = []
    for scheme in schemes:
        entries = [e for e in corpus
                   if e["subject"] == scheme.subject
                   and e["class_level"] == scheme.class_level]
        duration = 45 if scheme.class_level == B6 else 60
        config = build_config(scheme.subject, scheme.class_level, duration)
        job = GenerationPipeline().generate_all(scheme, config)
        plans = sorted(job._lesson_plans, key=lambda lp: (lp.week_number,
                                                          lp.lesson_sequence))
        assert len(plans) == len(entries), (
            f"{scheme.subject.value}/{scheme.class_level.value}: expected "
            f"{len(entries)} lessons, got {len(plans)}")
        # Plans arrive in week order and, inside a week, in indicator order —
        # the same order the entries were grouped in.
        for entry, lp in zip(entries, plans):
            results.append((entry, lp))
    return results


def score_corpus(corpus, label):
    results = []
    for entry, lp in run_generation(corpus):
        scored = base.score_lesson(entry, lp)
        scored["corpus"] = label
        results.append(scored)
    ready = sum(1 for r in results if r["teacher_ready"])
    summary = {
        "corpus": label,
        "lessons": len(results),
        "subjects": sorted({r["subject"] for r in results}),
        "teacher_ready": ready,
        "teacher_ready_rate": round(ready / len(results), 3) if results else 0.0,
        "mean_total": round(sum(r["total"] for r in results) / len(results), 1)
        if results else 0,
        "mean_scores": {
            name: round(sum(r["scores"][name] for r in results) / len(results), 2)
            for name, _ in base.RUBRIC
        },
        "hard_failure_counts": {},
        "ai_mode": "OFF",
        "zeli": "OFF",
    }
    for r in results:
        for f in r["hard_failures"]:
            summary["hard_failure_counts"][f] = (
                summary["hard_failure_counts"].get(f, 0) + 1)
    return {"summary": summary, "lessons": results}


def run_benchmark():
    return {
        "expanded": score_corpus(CORPUS, "expanded"),
        "messy": score_corpus(MESSY_CORPUS, "messy"),
    }


def _print_report(report):
    for label in ("expanded", "messy"):
        summary = report[label]["summary"]
        print(f"\n== {label} corpus (AI OFF, Zeli OFF) ==")
        print(f'lessons: {summary["lessons"]}  subjects: '
              f'{", ".join(summary["subjects"])}')
        print(f'teacher-ready: {summary["teacher_ready"]}/{summary["lessons"]} '
              f'({summary["teacher_ready_rate"] * 100:.0f}%)  '
              f'mean rubric: {summary["mean_total"]}/75')
        print("\n%-34s %5s  %-4s %s" % ("indicator", "total", "ready", "failures"))
        for r in report[label]["lessons"]:
            label_txt = f'{r["code"]} {r["indicator"]}'[:34]
            print("%-34s %5d  %-4s %s" % (
                label_txt, r["total"], "YES" if r["teacher_ready"] else "no",
                ", ".join(r["hard_failures"])))
        print("\nmean criterion scores:")
        for name, value in summary["mean_scores"].items():
            print(f"  {name:26s} {value}")
        if summary["hard_failure_counts"]:
            print("\nhard failures:")
            for name, count in sorted(summary["hard_failure_counts"].items()):
                print(f"  {name:26s} {count}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="", help="write JSON results here")
    args = parser.parse_args(argv)

    report = run_benchmark()
    _print_report(report)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False)
        print(f"\nwritten: {args.out}")
    return report


if __name__ == "__main__":
    main()

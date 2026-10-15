"""Phase 1 — P4 measurable-verb false-positive correction (chain tests).

The canonical rubric previously hard-rejected objectives whose outcome verb
was legitimate on the official curriculum but missing from its stale verb
inventory (``add``, ``multiply``, ``install``, ``indicate``, ``assess``,
``relate``, ``recognise``, ``skip count``, French ``écouter``/``lire``), and
pass-via-substring accidents (``household`` → ``use``, ``performance`` →
``perform``). This file pins the corrected chain:

    FULL indicator → deterministic objective (GenerationPipeline, AI OFF)
    → canonical rubric interpretation (lesson_rubric)
    → P4 gate decision (lesson_quality_gate, the runtime gate).

Genuine weak objectives must still be rejected: a measurable verb cannot
rescue an objective whose stated outcome does not express the indicator's
learning, and thresholds were NOT lowered.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from src.curriculum.indicator_actions import (
    leading_action,
    outcome_action,
)
from src.curriculum.lesson_rubric import (
    first_indicator_verb,
    hard_failures as rubric_hard_failures,
    score_lesson,
)
from src.models import (
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


def _entry(subject, cls, week, code, indicator, strand, sub_strand,
           cs_code, content_standard, resources, provenance):
    return dict(
        subject=subject, class_level=cls, week=week, code=code,
        indicator=indicator, strand=strand, sub_strand=sub_strand,
        content_standard_code=cs_code, content_standard=content_standard,
        resources=list(resources), provenance=provenance, group="",
    )


# The P2.1-audited false-rejected cases: every entry previously hard-failed
# with ``generic_objective`` (9 of the 14 gate rejections across the frozen
# corpora) despite producing a verb-led, indicator-aligned objective.
AFFECTED = [
    dict(subject=Subject.MATHEMATICS, cls=B7, week=4, code="B7.1.1.1.1",
         indicator="Add whole numbers up to 10,000",
         strand="Number", sub_strand="Number and Numeration",
         cs_code="B7.1.1.1", content_standard="B7.1.1.1 Number",
         lead="add",
         resources=["counters and bundles of sticks", "place-value chart",
                    "number cards", "exercise books and pencils"]),
    dict(subject=Subject.MATHEMATICS, cls=B7, week=5, code="B7.1.1.2.1",
         indicator="Multiply two-digit numbers by two-digit numbers",
         strand="Number", sub_strand="Number and Numeration",
         cs_code="B7.1.1.1", content_standard="B7.1.1.1 Number",
         lead="multiply",
         resources=["counters and bundles of sticks", "place-value chart",
                    "number cards", "exercise books and pencils"]),
    dict(subject=Subject.ICT, cls=B7, week=4, code="B7.1.1.2",
         indicator="Install an operating system.",
         strand="Introduction to Computing", sub_strand="Operating Systems",
         cs_code="B7.1.1.2",
         content_standard="B7.1.1.2 Install an operating system",
         lead="install",
         resources=["computer or unplugged steps on the board",
                    "exercise books"]),
    dict(subject=Subject.GHANAIAN_LANGUAGE, cls=B6, week=5,
         code="B6.1.4.1.1",
         indicator="B6.1.4.1.1 : Indicate the similarities and differences "
                   "between folktales and stories",
         strand="Oral Language",
         sub_strand="Listening and storytelling", cs_code="B6.1.4.1",
         content_standard="B6.1.4.1 : Demonstrate an understanding and "
                          "comparison of folktales to stories",
         lead="indicate", resources=["Word cards"]),
    dict(subject=Subject.HISTORY, cls=B6, week=1, code="B6.3.4.1.1",
         indicator="B6.3.4.1.1 Assess the changes that the European "
                   "presence brought to Ghana",
         strand="Europeans in Ghana", sub_strand="Impact of European presence",
         cs_code="B6.3.4.1",
         content_standard="B6.3.4.1 Demonstrates knowledge of the impact of "
                          "European presence on Ghana",
         lead="assess", resources=["A map of Ghana posters documentary"]),
    dict(subject=Subject.ENGLISH, cls=B6, week=7, code="B6.1.3.1.1",
         indicator="B6.1.3.1.1 : Relate the central messages of poems to "
                   "personal experiences.",
         strand="Oral Language", sub_strand="Poem", cs_code="B6.1.3.1",
         content_standard="B6.1.3.1 : Appreciate poems and other pieces of "
                          "literary materials",
         lead="relate", resources=["Word cards", "Flash Cards"]),
    dict(subject=Subject.GHANAIAN_LANGUAGE, cls=B6, week=2,
         code="B6.6.1.1.1",
         indicator="B6.6.1.1.1 : Recognise topics for magazine",
         strand="Reading", sub_strand="Phonics", cs_code="B6.6.1.1",
         content_standard="B6.6.1.1 : Exhibit knowledge of understanding and "
                          "appreciating magazines",
         lead="recognise",
         resources=["Letter cards", "Magazines", "Word cards", "Sentence cards"],
         # the thin source row's outcome verb is legitimately reworded to the
         # official exemplar's measurable verb ("use …") — accepted by design
         allow_lead_override=True),
    dict(subject=Subject.MATHEMATICS, cls=B6, week=6, code="B6.1.1.1.6",
         indicator="B6.1.1.1.6 : Skip count forwards and backwards in 5,000s, "
                   "10,000s, etc. up to and from 1,000,000.",
         strand="Number", sub_strand="Number and Numeration",
         cs_code="B6.1.1.1",
         content_standard="B6.1.1.1 : Demonstrate understanding of numbers "
                          "up to 1,000,000",
         lead="skip count", resources=["Counters", "number cards"]),
    dict(subject=Subject.FRENCH, cls=B6, week=6, code="B6.1.3.3.1",
         indicator=("B6.1.3.3.1 Écouter le dialogue et répéter les "
                    "expressions de salutation"),
         strand="L'identité", sub_strand="Présenter quelqu'un",
         cs_code="B6.1.3.1", content_standard="B6.1.3.1 Présenter quelqu'un",
         lead="écouter", resources=["L'ordinateur", "Video dialogue"]),
    dict(subject=Subject.FRENCH, cls=B6, week=8, code="B6.1.4.3.1",
         indicator=("B6.1.4.3.1 Lire et comprendre des textes simples sur "
                    "les caractéristiques physiques d'une personne"),
         strand="L'identité", sub_strand="Décrire quelqu'un",
         cs_code="B6.1.4.1", content_standard="B6.1.4.1 (Décrire quelqu'un)",
         lead="lire", resources=["L'ordinateur", "Texte dialogue"]),
]


def _one_entry_scheme_config(entry):
    week = Week(
        week_number=entry["week"],
        start_date=date(2026, 9, 7), end_date=date(2026, 9, 11),
        week_type=WeekType.INSTRUCTION,
        strand=entry["strand"], sub_strand=entry["sub_strand"],
        content_standards=[entry["content_standard"]],
        indicators=[f'{entry["code"]} {entry["indicator"]}'],
        resources=list(entry["resources"]),
        scheme_of_work_id="phase1-chain",
    )
    scheme = SchemeOfWork(
        id="phase1-chain", filename="phase1-chain.docx",
        class_level=entry["class_level"], subject=entry["subject"],
        term="First Term", academic_year="2026/2027",
        weeks=[week], upload_date=date(2026, 9, 1),
    )
    config = TermConfig(
        scheme_of_work_id="phase1-chain", academic_year="2026/2027",
        term="First Term", class_level=entry["class_level"],
        subject=entry["subject"],
        term_start_date=date(2026, 9, 7), term_end_date=date(2026, 12, 18),
        lessons_per_week=1, lesson_duration_minutes=60,
        teaching_days=[0], holidays=[], ai_mode=AIMode.OFF,
        school_name="Phase1 School", teacher_name="Phase1 Teacher",
    )
    return scheme, config


def _generate(entry):
    from src.engines.generation_pipeline import GenerationPipeline
    scheme, config = _one_entry_scheme_config(entry)
    job = GenerationPipeline().generate_all(scheme, config)
    plans = list(job._lesson_plans)
    assert plans, "pipeline produced no lesson for the entry"
    return plans[0]


@pytest.mark.parametrize("case", AFFECTED, ids=lambda c: c["lead"])
def test_chain_indicator_to_objective_to_rubric_to_gate(case):
    """FULL indicator → deterministic objective → rubric → P4 gate ACCEPT."""
    entry = _entry(case["subject"], case["cls"], case["week"], case["code"],
                   case["indicator"], case["strand"], case["sub_strand"],
                   case["cs_code"], case["content_standard"],
                   case["resources"], "Phase 1 chain fixture")
    lp = _generate(entry)

    # 1. deterministic objective states a measurable outcome verb, and is
    #    normally the indicator's own primary action (the official exemplar
    #    verb may override a thin source row — by accepted design)
    obj = lp.learning_objectives[0].description
    assert outcome_action(obj) != "", obj
    if not case.get("allow_lead_override"):
        assert outcome_action(obj) == case["lead"], obj
    # and the objective stays related to the indicator (no recall collapse)
    assert rubric_hard_failures(entry, lp) == [], (
        obj, rubric_hard_failures(entry, lp))

    # 2. canonical rubric interpretation agrees with the shared canon
    assert first_indicator_verb(entry["indicator"]) == case["lead"]

    # 3. P4 gate (runtime wrapper) accepts the lesson
    from src.engines.lesson_quality_gate import hard_failures as gate_failures
    failures = gate_failures(lp, entry)
    assert failures == [], failures

    # 4. teacher-ready floors hold
    scores = score_lesson(entry, lp)["scores"]
    assert scores["objective_specificity"] >= 4


def test_first_indicator_verb_matches_shared_canon():
    for case in AFFECTED:
        assert first_indicator_verb(case["indicator"]) == case["lead"], \
            case["indicator"]


# ── Weak objectives must keep being rejected ────────────────────────────────


def _weak_lp(indicator, objective, *, activity_text=None):
    """Minimal stored-lesson object for rubric-level negative tests."""
    return SimpleNamespace(
        learning_objectives=[SimpleNamespace(description=objective)],
        indicators=[f"B7.1.1.2.1 {indicator}"],
        content_standard="Demonstrate understanding of computer systems",
        lesson_topic="Operating systems",
        introduction="Teacher introduces the topic with a chart.",
        starter_activity="Learners name devices they know.",
        main_activities=[SimpleNamespace(
            phase="PHASE 2", duration_minutes=30, week_number=1,
            lesson_sequence=1, template_id="",
            description=activity_text or (
                "Learners work in pairs to distinguish between manual and "
                "automatic devices using the component chart, sorting "
                "picture cards into two labelled columns and recording "
                "their groups in exercise books with reasons."))],
        learner_activities=[
            SimpleNamespace(description="Learners sort the picture cards "
                                       "into manual and automatic columns "
                                       "and record the groups."),
        ],
        teacher_activities=[
            SimpleNamespace(description="Teacher introduces the chart and "
                                       "guides the sorting discussion."),
        ],
        assessment="Learners list two manual and two automatic devices.",
        class_assignment="", home_assignment="",
        conclusion="Teacher summarises the two device groups and learners "
                   "state one device each.",
        teaching_learning_resources=["component chart", "picture cards",
                                     "exercise books"],
        duration_minutes=60,
        references=[], structured_references=[],
        template_id="",
    )


@pytest.mark.parametrize("objective", [
    "learners will discuss the topic",
    "Learners can explore the topic",
    "Learners can learn about the generations of computers",
])
def test_vague_objectives_still_hard_rejected(objective):
    entry = _entry(Subject.ICT, B7, 1, "B7.1.1.1.1",
                   "Distinguish between manual and automatic devices",
                   "Introduction to Computing",
                   "Components of Computers and Computer Systems",
                   "B7.1.1.1",
                   "Demonstrate understanding of computer systems",
                   ["chart"], "negative-fixture")
    failures = rubric_hard_failures(entry, _weak_lp(
        "Distinguish between manual and automatic devices", objective))
    assert "generic_objective" in failures, (objective, failures)


def test_measurable_word_elsewhere_does_not_rescue_weak_outcome():
    """A measurable verb somewhere in the sentence is NOT an assessable
    outcome (word-boundary outcome-slot interpretation, not 'any match')."""
    entry = _entry(Subject.ICT, B7, 1, "B7.1.1.1.1",
                   "Demonstrate understanding of computer systems",
                   "Introduction to Computing",
                   "Components of Computers and Computer Systems",
                   "B7.1.1.1",
                   "Demonstrate understanding of computer systems",
                   ["chart"], "negative-fixture")
    # outcome slot carries a noun phrase; "use" appears only later embedded
    obj = ("Learners can acquire knowledge on components of computer "
           "systems and the uses of each component")
    failures = rubric_hard_failures(entry, _weak_lp(
        "identify hardware components", obj))
    assert "generic_objective" in failures, (obj, failures)


# ── Word-boundary / interpretation guarantees ───────────────────────────────


def test_word_boundary_no_accidental_substring_matches():
    # "household" must no longer count as "use"; "performance" no longer
    # counts as "perform" standing in for "assess".
    assert outcome_action("Learners can assess his/her own performance") \
        == "assess"
    assert outcome_action("Learners can install household appliances") \
        == "install"
    # a noun-lead objective (no action in the outcome slot) fails
    assert outcome_action("Learners can operating systems and devices") == ""


def test_later_generic_mention_does_not_override_intent():
    # The FIRST action after "Learners … will" is the instructional intent;
    # a later generic mention never becomes the outcome verb.
    obj = ("Learners can compare fractions with the same denominator and "
           "later discuss their strategies with the class")
    assert outcome_action(obj) == "compare"


def test_indicator_verb_alignment_is_primary_first():
    ind = "B9.1.2.1.1 Compare and contrast weather patterns in Ghana"
    assert leading_action(ind) == "compare"
    assert first_indicator_verb(ind) == "compare"

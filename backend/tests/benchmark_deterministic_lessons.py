"""Priority 2 — Deterministic lesson-authoring benchmark (BEFORE/AFTER).

Runs the REAL deterministic generation path (GenerationPipeline, AI OFF, Zeli
OFF) over a fixed corpus of real SchemeKnit curriculum occurrences spanning
Mathematics, Science, English, Computing, Creative Arts and Social Studies,
then scores every lesson on the fixed 15-criterion rubric (1-5, max 75) plus
the hard-failure list from the Priority 2 spec.

Usage (from backend/):
    ./venv/Scripts/python tests/benchmark_deterministic_lessons.py --out ../docs/benchmark/before.json

A lesson counts as TEACHER-READY only when it has no hard failures, exact
timing, an indicator-specific objective, three concrete phases, an aligned
assessment and usable resources. Scores are deterministic heuristics over the
stored lesson text — no AI is involved at any point.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.models import (  # noqa: E402
    AIMode,
    ClassLevel,
    SchemeOfWork,
    Subject,
    TermConfig,
    Week,
    WeekType,
)

# ── Benchmark corpus ────────────────────────────────────────────────────────
#
# Every entry is a REAL existing SchemeKnit curriculum occurrence: indicator
# texts are either verbatim NaCCA indicators already used as fixtures in this
# repository, or the official-corpus learning focus of a registered exemplar
# record (src/curriculum/exemplars). Provenance is recorded per entry.

BASIC7 = ClassLevel.BASIC_7

CORPUS = [
    # Mathematics (incl. the required repeated indicator across weeks)
    dict(
        subject=Subject.MATHEMATICS, class_level=BASIC7, week=1,
        code="B7.1.1.1.1",
        indicator="Use place value to read and write numbers",
        strand="Number", sub_strand="Number and Numeration Systems",
        content_standard_code="B7.1.1.1",
        content_standard="Demonstrate understanding of place value of digits in whole numbers",
        resources=["multi-base blocks", "place value chart", "exercise books"],
        provenance="NaCCA B7 indicator used in tests/test_curriculum_v2.py; exemplar record B7.1.1.1.1",
    ),
    dict(
        subject=Subject.MATHEMATICS, class_level=BASIC7, week=2,
        code="B7.1.1.1.1",
        indicator="Use place value to read and write numbers",
        strand="Number", sub_strand="Number and Numeration Systems",
        content_standard_code="B7.1.1.1",
        content_standard="Demonstrate understanding of place value of digits in whole numbers",
        resources=["multi-base blocks", "place value chart", "exercise books"],
        provenance="REPEAT of week 1 occurrence (progression probe)",
    ),
    dict(
        subject=Subject.MATHEMATICS, class_level=BASIC7, week=3,
        code="B7.1.1.1.3",
        indicator="Solve word problems involving addition and subtraction",
        strand="Number", sub_strand="Number and Numeration Systems",
        content_standard_code="B7.1.1.1",
        content_standard="Apply number operations to solve everyday problems",
        resources=["exercise books", "chalkboard", "word problem cards"],
        provenance="SchemeKnit fixture occurrence (tests/test_generation_quality_v3.py MATH_CODES)",
    ),
    # Science
    dict(
        subject=Subject.SCIENCE, class_level=BASIC7, week=1,
        code="B7.1.1.1.1",
        indicator="Classify materials as solids, liquids and gases",
        strand="Matter", sub_strand="Classification of Materials",
        content_standard_code="B7.1.1.1",
        content_standard="Demonstrate understanding of the states of matter",
        resources=["local samples (water, sand, stone)", "containers", "recording sheets"],
        provenance="Exemplar record B7/JHS1.1.1.1.1 (src/curriculum/exemplars/science.py)",
    ),
    dict(
        subject=Subject.SCIENCE, class_level=BASIC7, week=2,
        code="B7.2.1.1.1",
        indicator="Describe the characteristics of living things",
        strand="Diversity of Life", sub_strand="Living Things",
        content_standard_code="B7.2.1.1",
        content_standard="Demonstrate understanding of characteristics of living things",
        resources=["leaf samples", "chalkboard", "exercise books"],
        provenance="SchemeKnit fixture occurrence (tests/test_generation_quality_v3.py SCI_CODES)",
    ),
    # English Language
    dict(
        subject=Subject.ENGLISH, class_level=BASIC7, week=1,
        code="B7.1.1.1.1",
        indicator="Use formal and informal register in conversation",
        strand="Communication", sub_strand="Speaking and Listening",
        content_standard_code="B7.1.1.1",
        content_standard="Demonstrate the ability to communicate appropriately in different situations",
        resources=["conversation cards", "chalkboard", "exercise books"],
        provenance="Exemplar record B7/JHS1.1.1.1.1 (src/curriculum/exemplars/english.py)",
    ),
    dict(
        subject=Subject.ENGLISH, class_level=BASIC7, week=2,
        code="B7.1.1.1.2",
        indicator="Ask questions to elicit elaboration in conversation",
        strand="Communication", sub_strand="Speaking and Listening",
        content_standard_code="B7.1.1.1",
        content_standard="Demonstrate the ability to communicate appropriately in different situations",
        resources=["question cards", "chalkboard", "exercise books"],
        provenance="Exemplar record B7/JHS1.1.1.1.2 (src/curriculum/exemplars/english.py)",
    ),
    # Computing
    dict(
        subject=Subject.ICT, class_level=BASIC7, week=1,
        code="B7.1.1.1.2",
        indicator="Distinguish between manual and automatic devices",
        strand="Introduction to Computing", sub_strand="Components of Computers and Computer Systems",
        content_standard_code="B7.1.1.1",
        content_standard="Demonstrate understanding of computer systems and their components",
        resources=["sample input devices (keyboard, mouse, scanner)", "chart", "exercise books"],
        provenance="Fixture occurrence (tests/test_lesson_quality_remediation.py) + exemplar record B7.1.1.1.2",
    ),
    dict(
        subject=Subject.ICT, class_level=BASIC7, week=2,
        code="B7.1.1.2.1",
        indicator="Demonstrate how to use the Start screen, tiles and taskbar",
        strand="Introduction to Computing", sub_strand="Windows and the Desktop",
        content_standard_code="B7.1.1.2",
        content_standard="Demonstrate understanding of the operating system and its interface",
        resources=["computer or projected screen where available", "unplugged keyboard diagram", "exercise books"],
        provenance="Derived from exemplar record B7.1.1.2.1 learning focus + curriculum action verbs",
    ),
    # Creative Arts & Design
    dict(
        subject=Subject.CREATIVE_ARTS, class_level=BASIC7, week=1,
        code="B7.5.1.1.1",
        indicator="Create a simple pattern using local materials",
        strand="Design", sub_strand="Pattern and Decoration",
        content_standard_code="B7.5.1.1",
        content_standard="Demonstrate ability to create designs and works using local materials",
        resources=["local materials (seeds, leaves, cloth scraps)", "manila paper", "glue"],
        provenance="SchemeKnit fixture occurrence (tests/test_generation_quality_v3.py CRE_CODES)",
    ),
    # Social Studies
    dict(
        subject=Subject.SOCIAL_STUDIES, class_level=BASIC7, week=1,
        code="B7.1.1.2.1",
        indicator="Explain sources of energy in Ghana and ways of conserving energy",
        strand="Our Environment", sub_strand="Energy Resources",
        content_standard_code="B7.1.1.2",
        content_standard="Demonstrate understanding of energy resources and their conservation",
        resources=["chart of local energy sources", "chalkboard", "exercise books"],
        provenance="Exemplar record B7/JHS1 1.1.2.1 (src/curriculum/exemplars/social_studies.py)",
    ),
]

# Canonical rubric (shared with the runtime quality gate) re-exported so
# existing imports of this module (benchmark_hardening, scripts) keep
# working — scoring code lives ONLY in src/curriculum/lesson_rubric.py.
from src.curriculum.lesson_rubric import (  # noqa: F401
    SUBJECT_STRAND_KEY,
    _STOPWORDS,
    _MEASURABLE_VERBS,
    _GENERIC_OBJECTIVE_RE,
    _FILLER_PATTERNS,
    _PLACEHOLDER_REF_RE,
    _IMPOSSIBLE_RESOURCES,
    _COMMON_RESOURCES,
    _GROUPING_RE,
    _QUANTITY_RE,
    _PRODUCT_RE,
    _TEACHER_VERBS,
    _MONITOR_RE,
    _EVIDENCE_RE,
    _CLOSURE_RE,
    _STARTER_ACTION_RE,
    _SUBJECT_MARKERS,
    _GHANA_CONTEXT_RE,
    content_words,
    overlap_recall,
    distinct_markers,
    first_indicator_verb,
    verb_stem_matches,
    phase_rows,
    lesson_body,
    c01_indicator_fidelity,
    c02_objective_specificity,
    c03_topic_specificity,
    c04_phase1_usefulness,
    _COMMON_CONNECT,
    c05_phase2_usefulness,
    c06_phase3_usefulness,
    c07_activity_specificity,
    c08_teacher_action_clarity,
    c09_learner_action_clarity,
    c10_assessment_alignment,
    c11_resource_realism,
    c12_timing_integrity,
    c13_subject_pedagogy_fit,
    c14_ghana_context,
    c15_teachability,
    RUBRIC,
    hard_failures,
    teacher_ready,
    score_lesson,
)



def build_scheme(entry_list):
    """One SchemeOfWork per subject, one Week per source occurrence."""
    weeks = []
    for entry in entry_list:
        weeks.append(Week(
            week_number=entry["week"],
            start_date=date(2026, 9, 7) + (date(2026, 9, 14) - date(2026, 9, 7)) * (entry["week"] - 1),
            end_date=date(2026, 9, 11) + (date(2026, 9, 18) - date(2026, 9, 11)) * (entry["week"] - 1),
            week_type=WeekType.INSTRUCTION,
            strand=entry["strand"], sub_strand=entry["sub_strand"],
            content_standards=[entry["content_standard"]],
            indicators=[f'{entry["code"]} {entry["indicator"]}'],
            resources=list(entry["resources"]),
            scheme_of_work_id="bench",
        ))
    first = entry_list[0]
    return SchemeOfWork(
        id="bench", filename="benchmark.docx",
        class_level=first["class_level"], subject=first["subject"],
        term="First Term", academic_year="2026/2027",
        weeks=weeks, upload_date=date(2026, 9, 1),
    )


def build_config(subject, class_level):
    return TermConfig(
        scheme_of_work_id="bench", academic_year="2026/2027", term="First Term",
        class_level=class_level, subject=subject,
        term_start_date=date(2026, 9, 7), term_end_date=date(2026, 12, 18),
        lessons_per_week=1, lesson_duration_minutes=60,
        teaching_days=[0], holidays=[], ai_mode=AIMode.OFF,
        school_name="Benchmark School", teacher_name="Benchmark Teacher",
    )


def run_generation():
    """Generate lessons for every corpus subject on the real pipeline.

    Returns a list of (entry, lesson) pairs in corpus order.
    """
    from src.engines.generation_pipeline import GenerationPipeline

    by_subject = {}
    for entry in CORPUS:
        by_subject.setdefault(entry["subject"], []).append(entry)

    results = []
    for subject, entries in by_subject.items():
        scheme = build_scheme(entries)
        config = build_config(subject, entries[0]["class_level"])
        job = GenerationPipeline().generate_all(scheme, config)
        plans = sorted(job._lesson_plans, key=lambda lp: (lp.week_number, lp.lesson_sequence))
        assert len(plans) == len(entries), (
            f"{subject}: expected {len(entries)} lessons, got {len(plans)}")
        for entry, lp in zip(entries, plans):
            results.append((entry, lp))
    return results


def run_benchmark():
    results = []
    for entry, lp in run_generation():
        results.append(score_lesson(entry, lp))
    ready = sum(1 for r in results if r["teacher_ready"])
    summary = {
        "lessons": len(results),
        "subjects": sorted({r["subject"] for r in results}),
        "teacher_ready": ready,
        "teacher_ready_rate": round(ready / len(results), 3) if results else 0.0,
        "mean_total": round(sum(r["total"] for r in results) / len(results), 1) if results else 0,
        "mean_scores": {
            name: round(sum(r["scores"][name] for r in results) / len(results), 2)
            for name, _ in RUBRIC
        },
        "hard_failure_counts": {},
        "ai_mode": "OFF",
        "zeli": "OFF",
    }
    for r in results:
        for f in r["hard_failures"]:
            summary["hard_failure_counts"][f] = summary["hard_failure_counts"].get(f, 0) + 1
    return {"summary": summary, "lessons": results}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="", help="write JSON results here")
    args = parser.parse_args(argv)

    report = run_benchmark()
    summary = report["summary"]

    print("\n== Deterministic lesson benchmark (AI OFF) ==")
    print(f'lessons: {summary["lessons"]}  subjects: {", ".join(summary["subjects"])}')
    print(f'teacher-ready: {summary["teacher_ready"]}/{summary["lessons"]} '
          f'({summary["teacher_ready_rate"] * 100:.0f}%)  mean rubric: {summary["mean_total"]}/75')
    print("\n%-28s %5s  %-4s %s" % ("indicator", "total", "ready", "failures"))
    for r in report["lessons"]:
        label = f'{r["code"]} {r["indicator"]}'[:28]
        print("%-28s %5d  %-4s %s" % (
            label, r["total"], "YES" if r["teacher_ready"] else "no",
            ", ".join(r["hard_failures"])))
    print("\nmean criterion scores:")
    for name, value in summary["mean_scores"].items():
        print(f"  {name:26s} {value}")
    if summary["hard_failure_counts"]:
        print("\nhard failures:")
        for name, count in sorted(summary["hard_failure_counts"].items()):
            print(f"  {name:26s} {count}")

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False)
        print(f"\nwritten: {args.out}")
    return report


if __name__ == "__main__":
    main()

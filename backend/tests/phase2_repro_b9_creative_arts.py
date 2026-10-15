"""Phase 2 — reproduce the REA historical SchemeKnit artifact on CURRENT code.

The old REA comparison (``docs/research/rea/LESSON_QUALITY_COMPARISON.md``)
scored a SchemeKnit lesson at 40/75 with strand-concat topic, slot-fill prose
artefacts ("…using ;") and 32/50-minute phase timing. That artifact
(``docs/research/ghanaed/schemeknit_benchmark_lesson.json``; provenance in
``schemeknit_benchmark_provenance.json``) predates P2/P2.1. This script
replays its exact inputs (Basic 9 Creative Arts & Design, B9.1.3.1.1,
50 minutes, the same scheme TLRs, AI OFF / Zeli OFF) on the CURRENT pipeline
and records what the current engine produces, including the canonical rubric
score and hard-failure list.

Usage (from backend/):
    python tests/phase2_repro_b9_creative_arts.py --out ../docs/benchmark/phase2_reproduction_b9_creative_arts.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.models import (  # noqa: E402
    AIMode, ClassLevel, SchemeOfWork, Subject, TermConfig, Week, WeekType,
)

INDICATOR_CODE = "B9.1.3.1.1"
INDICATOR_TEXT = "Plan and execute design projects using the creative process."
STRAND = "DESIGN"
SUB_STRAND = "CREATIVE AND DESIGN PROCESSES"
CONTENT_STANDARD = "B9.1.3.1 Apply the creative process to manage design projects."
SOURCE_TLRS = ["Manila paper", "Markers", "Chart paper"]


def build():
    week = Week(
        week_number=1, start_date=date(2026, 10, 5), end_date=date(2026, 10, 9),
        week_type=WeekType.INSTRUCTION,
        strand=STRAND, sub_strand=SUB_STRAND,
        content_standards=[CONTENT_STANDARD],
        indicators=[f"{INDICATOR_CODE} {INDICATOR_TEXT}"],
        resources=list(SOURCE_TLRS),
        scheme_of_work_id="phase2",
    )
    scheme = SchemeOfWork(
        id="phase2", filename="sk_b9_creative_arts_scheme.docx",
        class_level=ClassLevel.BASIC_9, subject=Subject.CREATIVE_ARTS,
        term="First Term", academic_year="2026/2027",
        weeks=[week], upload_date=date(2026, 10, 1),
    )
    config = TermConfig(
        scheme_of_work_id="phase2", academic_year="2026/2027", term="First Term",
        class_level=ClassLevel.BASIC_9, subject=Subject.CREATIVE_ARTS,
        term_start_date=date(2026, 10, 1), term_end_date=date(2026, 12, 18),
        lessons_per_week=1, lesson_duration_minutes=50,
        teaching_days=[4], holidays=[], ai_mode=AIMode.OFF,
        school_name="", teacher_name="SK Benchmark Teacher",
    )
    return scheme, config


def run() -> dict:
    from src.engines.generation_pipeline import GenerationPipeline
    from src.curriculum.lesson_rubric import hard_failures, score_lesson

    scheme, config = build()
    job = GenerationPipeline().generate_all(scheme, config)
    lp = list(job._lesson_plans)[0]

    entry = dict(
        indicator=INDICATOR_TEXT, code=INDICATOR_CODE, week=1,
        subject=Subject.CREATIVE_ARTS, class_level=ClassLevel.BASIC_9,
        strand=STRAND, sub_strand=SUB_STRAND,
        content_standard="Apply the creative process to manage design projects.",
        content_standard_code="B9.1.3.1",
        resources=list(SOURCE_TLRS), provenance="", group="",
    )
    res = score_lesson(entry, lp)
    failures = hard_failures(entry, lp)

    return {
        "authored": "2026-10-15 (post-P4, current main)",
        "historical_artifact": {
            "file": "docs/research/ghanaed/schemeknit_benchmark_lesson.json",
            "note": "P1/P2-era deterministic output; preserved unmodified; "
                    "scored 40/75 by the REA study with strand-concat topic, "
                    "slot-fill prose ('…using ;') and 32/50-minute timing",
        },
        "inputs": {
            "scheme": "sk_b9_creative_arts_scheme.docx",
            "class_level": "Basic 9", "subject": "Creative Arts and Design",
            "indicator": f"{INDICATOR_CODE} {INDICATOR_TEXT}",
            "strand": STRAND, "sub_strand": SUB_STRAND,
            "content_standard": CONTENT_STANDARD,
            "duration_minutes": 50, "class_size": 30,
            "source_tlrs": SOURCE_TLRS,
            "ai_mode": "OFF", "zeli": "OFF",
            "inputs_comparable": True,
            "note": "identical source-week inputs as the archived artifact "
                    "(code, indicator text, strand, sub-strand, standard, "
                    "duration, scheme TLRs); lesson date/term dates are "
                    "equivalent equivalents of the artifact's 2026-10 week",
        },
        "generated": {
            "lesson_topic": lp.lesson_topic,
            "previous_knowledge": lp.previous_knowledge,
            "content_standard": lp.content_standard,
            "content_standard_code": lp.content_standard_code,
            "indicator_codes": lp.indicator_codes,
            "learning_objectives": [
                {"description": o.description, "indicator_code": o.indicator_code,
                 "source": getattr(o, "source", "")}
                for o in lp.learning_objectives],
            "core_competencies": lp.core_competencies,
            "source_tlrs": lp.source_tlrs,
            "teaching_learning_resources": lp.teaching_learning_resources,
            "starter_activity": lp.starter_activity,
            "introduction": lp.introduction,
            "main_activities": [
                {"phase": a.phase, "description": a.description,
                 "duration_minutes": a.duration_minutes,
                 "source": getattr(a, "source", "")}
                for a in lp.main_activities],
            "learner_activities": [a.description for a in lp.learner_activities],
            "teacher_activities": [a.description for a in lp.teacher_activities],
            "assessment": lp.assessment,
            "differentiation": lp.differentiation,
            "class_assignment": lp.class_assignment,
            "home_assignment": lp.home_assignment,
            "conclusion": lp.conclusion,
            "keywords": lp.keywords,
            "stored_minutes_total": sum(int(a.duration_minutes or 0)
                                        for a in lp.main_activities),
        },
        "canonical_rubric": {
            "scores": res["scores"], "total": res["total"],
            "teacher_ready": res["teacher_ready"],
            "hard_failures": failures,
            "note": "same 15-criterion canonical rubric the P4 gate enforces",
        },
        "historical_defect_reproduction": {
            "strand_concat_topic": lp.lesson_topic.strip().lower() in [
                "design - creative and design processes",
                f'{STRAND.lower()} - {SUB_STRAND.lower()}'],
            "slot_fill_artifacts": any(
                p in ((a.description or "").lower())
                for a in lp.main_activities
                for p in ("using ;", "using.", "process..", "{", "}")),
            "incomplete_timing": sum(int(a.duration_minutes or 0)
                                     for a in lp.main_activities) != 50,
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="",
                        help="write JSON evidence here")
    args = parser.parse_args(argv)
    result = run()
    print(json.dumps(result["historical_defect_reproduction"], indent=1))
    print("canonical rubric total:", result["canonical_rubric"]["total"],
          "teacher_ready:", result["canonical_rubric"]["teacher_ready"])
    print("topic:", result["generated"]["lesson_topic"])
    print("assessment:", result["generated"]["assessment"])
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=1, ensure_ascii=False, default=str)
        print("written:", args.out)
    return result


if __name__ == "__main__":
    main()

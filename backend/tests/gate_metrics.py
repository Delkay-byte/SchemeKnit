"""Priority 4 — quality-gate calibration run over the FROZEN corpora.

Runs the SAME gate the canonical generation path uses
(``routers.generation._run_quality_gate``) over the 11 / 40 / 19-lesson frozen
corpora (AI OFF, Zeli OFF) and prints + writes the gate metrics: first-pass
rate, mechanical repairs, rebuilds, rejections and scores.

Usage (from backend/):
    ./venv/Scripts/python tests/gate_metrics.py --out ../docs/benchmark/gate_metrics.json

The numbers are the calibration evidence recorded in docs/QUALITY_GATE.md:
they were produced BEFORE any threshold was tuned (the corpora are frozen) and
they show exactly which lessons the gate refuses and why.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import benchmark_deterministic_lessons as base  # noqa: E402
import benchmark_hardening as hardening  # noqa: E402

from src.engines.allocation_engine import AllocationEngine, BuildLedger  # noqa: E402
from src.engines.calendar_engine import CalendarEngine  # noqa: E402
from src.routers.generation import _run_quality_gate  # noqa: E402


def _generate(entries, duration):
    """One (plans, ledger, config) per subject bucket, merged in corpus order."""
    by_subject: dict = {}
    for entry in entries:
        key = (entry["subject"], entry["class_level"])
        by_subject.setdefault(key, []).append(entry)
    jobs = []
    for (subject, class_level), group in by_subject.items():
        scheme = base.build_scheme(group)
        config = hardening.build_config(subject, class_level, duration)
        calendar = CalendarEngine().build_calendar(config, scheme.weeks, [])
        coverage = AllocationEngine().allocate(scheme.weeks, calendar, config)
        ledger = BuildLedger()
        plans = AllocationEngine().generate_lesson_plans(
            coverage, config, "gate-calibration", ledger=ledger)
        jobs.append((plans, ledger, config, scheme.id))
    return jobs


def run_corpus(label, entries, duration):
    merged_metrics = None
    per_lesson = []
    total_lessons = 0
    for plans, ledger, config, scheme_id in _generate(entries, duration):
        job = SimpleNamespace(_lesson_plans=plans, _build_ledger=ledger)
        report = _run_quality_gate(job, config, scheme_id, drafts={})
        per_lesson.extend(
            {
                "lesson_sequence": r.lesson_sequence,
                "indicator_code": r.indicator_code,
                "status": r.status,
                "attempts": r.attempts,
                "total": r.total,
                "hard_failures": r.hard_failures,
                "floors_failed": r.floors_failed,
                "repairs": r.repairs,
                "rebuild_pattern_ids": r.rebuild_pattern_ids,
            }
            for r in report["reports"]
        )
        m = report["metrics"]
        total_lessons += m["lessons"]
        if merged_metrics is None:
            merged_metrics = dict(m)
            merged_metrics.pop("first_pass_rate", None)
            merged_metrics.pop("teacher_ready_rate", None)
            merged_metrics.pop("mean_score", None)
            merged_metrics.pop("mean_rebuilds", None)
        else:
            for key in ("accepted", "rejected", "first_pass", "repaired", "rebuilt"):
                merged_metrics[key] += m[key]
            for key in ("hard_rejections", "soft_rejections", "repairs"):
                merged_metrics[key] = {
                    **merged_metrics[key], **{
                        k: merged_metrics[key].get(k, 0) + v
                        for k, v in m[key].items()}}
    n = total_lessons or 1
    merged_metrics.update(
        lessons=total_lessons,
        first_pass_rate=round(merged_metrics["first_pass"] / n, 3),
        teacher_ready_rate=round(merged_metrics["accepted"] / n, 3),
        mean_score=round(sum(p["total"] for p in per_lesson) / n, 1),
        mean_rebuilds=round(sum(p["attempts"] for p in per_lesson) / n, 2),
    )
    return {"summary": merged_metrics, "lessons": per_lesson}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="", help="write JSON results here")
    args = parser.parse_args(argv)

    report = {
        "11-lesson": run_corpus("11-lesson", base.CORPUS, 60),
        "expanded-40": run_corpus("expanded-40", hardening.CORPUS, 60),
        "messy-19": run_corpus("messy-19", hardening.MESSY_CORPUS, 45),
    }

    print("\n== Quality gate over the frozen corpora (AI OFF, Zeli OFF) ==")
    for name, group in report.items():
        s = group["summary"]
        print(f"\n{name}: {s['lessons']} lessons")
        print(f"  accepted: {s['accepted']}  first pass: {s['first_pass']}  "
              f"repaired: {s['repaired']}  rebuilt: {s['rebuilt']}  "
              f"rejected: {s['rejected']}")
        print(f"  first-pass rate: {s['first_pass_rate']:.0%}  "
              f"teacher-ready rate: {s['teacher_ready_rate']:.0%}  "
              f"mean rubric: {s['mean_score']}/75  mean rebuilds: {s['mean_rebuilds']}")
        if s["hard_rejections"]:
            print("  hard rejections: " + ", ".join(
                f"{k}×{v}" for k, v in sorted(s["hard_rejections"].items())))
        if s["soft_rejections"]:
            print("  soft rejections (floors): " + ", ".join(
                f"{k}×{v}" for k, v in sorted(s["soft_rejections"].items())))
        if s["repairs"]:
            print("  mechanical repairs: " + ", ".join(
                f"{k}×{v}" for k, v in sorted(s["repairs"].items())))

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False)
        print(f"\nwritten: {args.out}")
    return report


if __name__ == "__main__":
    main()

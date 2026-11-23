"""Controlled 15-lesson generation benchmark (no network, no paid calls).

Usage (from backend/):
    python tests/benchmark_generation_parallel.py --out ../docs/infrastructure/benchmarks/generation-parallel.json

Every run uses the SAME workload: 15 Mathematics/Basic 4 WAPEF-shaped lesson
units and a mock provider with a fixed 250 ms response delay. Worker counts
1/2/3/4 are compared with the pool size pinned for the run. The deterministic
engine is measured separately because it is CPU-bound and should not inherit
provider concurrency.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import threading
import time
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.models import (  # noqa: E402
    AIMode, ClassLevel, GenerationMethod, SchemeOfWork, Subject, TermConfig,
    Week, WeekType,
)

LATENCY_SECONDS = 0.25
LESSONS = 15


class FakeProvider:
    name = "groq"
    model = "benchmark-mock"

    def get_name(self):
        return self.name

    def is_available(self):
        return True


def _content(code="B4"):
    return {
        "learning_objectives": [
            f"Learners can use place value to read and write numbers ({code}).",
            f"Learners can explain the value of each digit to a partner ({code}).",
        ],
        "key_vocabulary": ["place value", "digit", "numeral"],
        "starter": {
            "activity": (
                "The teacher writes a four-digit number on the board and asks "
                "pairs to say the value of each digit before sharing answers."
            )
        },
        "main_learning": {
            "phase1": {
                "name": "Guided discovery",
                "activity": (
                    "Learners build four-digit numbers with place value cards "
                    "and state the value of each digit aloud."
                ),
                "duration_minutes": 20,
                "resources_used": ["Place value cards", "Chalkboard"],
            },
            "phase2": {
                "name": "Group task",
                "activity": (
                    "In groups, learners write three numbers in words and "
                    "exchange books to check each digit's value."
                ),
                "duration_minutes": 20,
            },
        },
        "assessment": {
            "method": "Observation",
            "activity": (
                "The teacher observes each group reading and writing a number, "
                "and records correct answers on a checklist."
            ),
        },
        "plenary": {
            "activity": (
                "Learners state one number in words and explain how place "
                "value helped them; the teacher checks every group's answer."
            )
        },
        "differentiation": {
            "support": "Pair with a peer and use place value cards.",
            "core": "Write three numbers in words.",
            "extension": "Create a five-digit number and explain each digit.",
        },
        "homework_or_extension": "List three numbers at home in words.",
    }


def _scheme(lessons=LESSONS):
    weeks = []
    for n in range(1, lessons + 1):
        weeks.append(Week(
            week_number=n,
            start_date=date(2026, 9, 7) + timedelta(days=(n - 1) * 7),
            end_date=date(2026, 9, 11) + timedelta(days=(n - 1) * 7),
            week_type=WeekType.INSTRUCTION,
            strand="Number",
            sub_strand="Number and Numeration Systems",
            content_standards=[f"B4.1.1.{n}"],
            indicators=[f"B4.1.1.{n}.1 Use place value to read and write numbers"],
            resources=["place value cards", "chalkboard", "exercise books"],
            scheme_of_work_id="bench",
        ))
    return SchemeOfWork(
        id="bench", filename="benchmark.docx",
        class_level=ClassLevel.BASIC_4, subject=Subject.MATHEMATICS,
        term="First Term", academic_year="2026/2027",
        weeks=weeks, upload_date=date(2026, 9, 1),
    )


def _config(method):
    return TermConfig(
        scheme_of_work_id="bench", academic_year="2026/2027",
        term="First Term", class_level="Basic 4", subject="Mathematics",
        term_start_date=date(2026, 9, 7), term_end_date=date(2026, 12, 18),
        lessons_per_week=1, lesson_duration_minutes=60, teaching_days=[0],
        holidays=[], ai_mode=AIMode.OFF, generation_method=method,
        template_id="tpl-wapef-approved-plan",
    )


def _run(method, workers, latency=LATENCY_SECONDS, fail_every=0):
    import src.engines.generation_pipeline as gp
    import src.engines.generation_concurrency as gc

    tracker = {"active": 0, "peak": 0, "started": [], "finished": [],
               "failures": 0, "calls": 0}
    lock = threading.Lock()

    def _generate(*, primary, fallback, context, db=None, user_id=None,
                  request_id=None):
        code = str(context.get("indicator_code") or "")
        with lock:
            tracker["active"] += 1
            tracker["peak"] = max(tracker["peak"], tracker["active"])
            tracker["calls"] += 1
            number = tracker["calls"]
        try:
            time.sleep(latency)
            if fail_every and number % fail_every == 0:
                with lock:
                    tracker["failures"] += 1
                from src.engines.zeli_generation import ZeliGenerationError
                raise ZeliGenerationError("Simulated provider failure", 502)
            return json.loads(json.dumps(_content(code))), {
                "provider": "groq", "model": "benchmark-mock",
                "attempts": [{"provider": "groq", "cache_hit": False}],
                "cache_hit": False, "external_calls": 1,
            }
        finally:
            with lock:
                tracker["active"] -= 1

    old_provider = gp.get_zeli_provider
    old_fallback = gp.get_zeli_fallback_provider
    old_generate = gp.generate_zeli_with_fallback
    old_workers = gc.effective_worker_count
    old_ai = gc.teacher_ai_concurrency_limit
    try:
        gp.get_zeli_provider = lambda: FakeProvider()
        gp.get_zeli_fallback_provider = lambda: None
        gp.generate_zeli_with_fallback = _generate
        gc.effective_worker_count = lambda *a, **k: int(workers)
        gc.teacher_ai_concurrency_limit = lambda: 99
        from src.engines.generation_pipeline import GenerationPipeline
        started = time.perf_counter()
        job = GenerationPipeline().generate_all(
            _scheme(), _config(method))
        elapsed = time.perf_counter() - started
    finally:
        gp.get_zeli_provider = old_provider
        gp.get_zeli_fallback_provider = old_fallback
        gp.generate_zeli_with_fallback = old_generate
        gc.effective_worker_count = old_workers
        gc.teacher_ai_concurrency_limit = old_ai

    timings = [
        float(t.get("total_seconds") or 0)
        for t in getattr(job, "_lesson_timings", [])
    ]
    timings_sorted = sorted(timings)
    p95 = (
        timings_sorted[max(0, int(round(0.95 * (len(timings_sorted) - 1))))]
        if timings_sorted else 0.0
    )
    return {
        "method": method.value if hasattr(method, "value") else str(method),
        "workers": int(workers),
        "expected": LESSONS,
        "generated": len(job._lesson_plans),
        "failures": len(getattr(job, "_generation_failures", []) or []),
        "total_seconds": round(elapsed, 4),
        "avg_lesson_seconds": round(statistics.mean(timings), 4) if timings else 0,
        "median_lesson_seconds": round(statistics.median(timings), 4) if timings else 0,
        "p95_lesson_seconds": round(p95, 4),
        "peak_simultaneous_provider_calls": tracker["peak"],
        "provider_calls": tracker["calls"],
        "stages": getattr(job, "_timings", {}),
        "duplicate_lesson_ids": len(job._lesson_plans) - len(
            {lp.id for lp in job._lesson_plans}),
        "curriculum_order_kept": [
            lp.lesson_sequence for lp in job._lesson_plans
        ] == sorted(lp.lesson_sequence for lp in job._lesson_plans),
    }


def _persistence_probe(lessons=LESSONS):
    """Measure durable insert cost separately from provider work."""
    import tempfile

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from src.database import Base, GenerationJobDB, LessonPlanDB, SchemeDB, User
    with tempfile.TemporaryDirectory() as tmp:
        engine = create_engine(f"sqlite:///{tmp}/bench.db")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            user = User(
                id="bench-user", email="bench@test.local", full_name="Bench",
                hashed_password="x",
            )
            scheme = SchemeDB(
                id="bench", owner_id=user.id, filename="bench.docx",
                subject="Mathematics", class_level="Basic 4",
            )
            job = GenerationJobDB(
                id="bench-job", owner_id=user.id, scheme_id=scheme.id,
                status="processing", config_snapshot={},
            )
            db.add_all([user, scheme, job])
            db.commit()
            rows = [
                LessonPlanDB(
                    id=f"lp-{n}", owner_id=user.id, job_id=job.id,
                    scheme_id=scheme.id, week_number=n,
                    lesson_sequence=n, subject="Mathematics",
                    class_level="Basic 4", indicator_codes=[f"B4.1.1.{n}.1"],
                    indicators=["Use place value"], strand="Number",
                    sub_strand="Number and Numeration Systems",
                    content_standard="Place value", source_occurrence_id=f"week{n}:0:B4.1.1.{n}.1",
                    status="generated",
                )
                for n in range(1, lessons + 1)
            ]
            started = time.perf_counter()
            db.add_all(rows)
            db.commit()
            return round(time.perf_counter() - started, 4)
        finally:
            db.close()
            engine.dispose()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="")
    parser.add_argument(
        "--latency", type=float, default=LATENCY_SECONDS,
        help="simulated provider latency per lesson in seconds")
    args = parser.parse_args(argv)

    results = []
    print(f"== 15-lesson controlled benchmark (mock latency {args.latency}s) ==")
    for workers in (1, 2, 3, 4):
        row = _run(GenerationMethod.ZELI, workers, args.latency)
        results.append(row)
        print(
            f"workers={workers}: total={row['total_seconds']:.2f}s "
            f"avg={row['avg_lesson_seconds']:.3f}s "
            f"p95={row['p95_lesson_seconds']:.3f}s "
            f"peak={row['peak_simultaneous_provider_calls']} "
            f"failures={row['failures']} generated={row['generated']}"
        )

    deterministic = _run(GenerationMethod.STANDARD, 1, 0)
    print(
        f"deterministic (AI off): total={deterministic['total_seconds']:.2f}s "
        f"generated={deterministic['generated']}"
    )
    persistence = _persistence_probe()
    print(f"15-row durable persistence probe: {persistence:.3f}s")

    baseline = results[0]["total_seconds"]
    for row in results:
        row["improvement_vs_sequential"] = round(
            baseline / row["total_seconds"], 2) if row["total_seconds"] else 0
        row["saved_seconds_vs_sequential"] = round(
            baseline - row["total_seconds"], 4)

    report = {
        "workload": {
            "lessons": LESSONS,
            "subject": "Mathematics",
            "class": "Basic 4",
            "template": "tpl-wapef-approved-plan",
            "mock_provider_latency_seconds": args.latency,
            "provider_calls_per_lesson": 1,
        },
        "concurrency": results,
        "deterministic": deterministic,
        "persistence_probe_seconds": persistence,
    }
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False)
        print(f"written: {args.out}")
    return report


if __name__ == "__main__":
    main()

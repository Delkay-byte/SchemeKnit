"""Controlled parallel lesson-unit generation.

The parent run owns ONE bounded worker pool. These tests use a controlled mock
provider (fixed latency, no network) to prove that:

* the pool is bounded (peak simultaneous calls never exceeds the configured
  worker count, and 1 worker stays strictly sequential);
* results keep curriculum order regardless of completion order;
* one failed unit never discards successful units and is reported per unit;
* a 429 refusal is retried inside the worker without duplicating a lesson;
* live progress receives one event per completed unit.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from datetime import date, timedelta

import pytest

sys.path.insert(0, "src")

from src.models import (  # noqa: E402
    AIMode, ClassLevel, GenerationMethod, SchemeOfWork, Subject, TermConfig,
    Week, WeekType,
)
from src.engines.generation_pipeline import GenerationPipeline  # noqa: E402
from src.engines.zeli_generation import ZeliGenerationError  # noqa: E402


def _full_lesson(marker="PARALLEL"):
    return {
        "learning_objectives": [
            f"Learners can identify a device and state one use ({marker}).",
            f"Learners can explain one use to a partner ({marker}).",
        ],
        "key_vocabulary": [f"{marker.lower()}_vocab"],
        "starter": {
            "activity": (
                f"{marker} starter: the teacher shows real classroom devices "
                "and asks learners in pairs to name each device and say one use."
            )
        },
        "main_learning": {
            "phase1": {
                "name": "Guided discovery",
                "activity": (
                    f"{marker} phase one: learners sort real classroom devices "
                    "into working and non-working groups, naming each one aloud."
                ),
                "duration_minutes": 20,
                "resources_used": ["Bottle caps", "Chart"],
            },
            "phase2": {
                "name": "Group task",
                "activity": (
                    f"{marker} phase two: in pairs, learners label a chart with "
                    "the name and one use of each device, then swap charts."
                ),
                "duration_minutes": 20,
            },
        },
        "assessment": {
            "method": "Observation",
            "activity": (
                f"{marker} assessment: the teacher observes each pair as they "
                "identify a device and match it to its use on a checklist."
            ),
        },
        "plenary": {
            "activity": (
                f"{marker} plenary: learners summarise in one sentence what they "
                "learned, and the teacher checks every pair can identify a device."
            )
        },
        "differentiation": {
            "support": f"{marker} support: pair with a peer",
            "core": f"{marker} core: complete the chart",
            "extension": f"{marker} extension: suggest a new device",
        },
        "homework_or_extension": f"{marker} homework: list three devices at home",
    }


class FakeProvider:
    def __init__(self, name="groq", model="parallel-test-model"):
        self.name = name
        self.model = model

    def get_name(self):
        return self.name

    def is_available(self):
        return True


def _scheme(weeks=6):
    week_rows = []
    for n in range(1, weeks + 1):
        week_rows.append(Week(
            week_number=n,
            start_date=date(2026, 9, 7) + timedelta(days=(n - 1) * 7),
            end_date=date(2026, 9, 11) + timedelta(days=(n - 1) * 7),
            week_type=WeekType.INSTRUCTION,
            strand="Computing",
            sub_strand="Hardware",
            content_standards=[f"B7.1.1.{n}"],
            indicators=[f"B7.1.1.{n}.1 Identify a device"],
            resources=["Chart"],
            scheme_of_work_id="parallel",
        ))
    return SchemeOfWork(
        id="parallel", filename="parallel.docx",
        class_level=ClassLevel.BASIC_7, subject=Subject.ICT,
        term="First Term", academic_year="2026/2027",
        weeks=week_rows, upload_date=date(2026, 9, 1),
    )


def _config():
    return TermConfig(
        scheme_of_work_id="parallel", academic_year="2026/2027",
        term="First Term", class_level="Basic 7", subject="ICT",
        term_start_date=date(2026, 9, 7), term_end_date=date(2026, 12, 18),
        lessons_per_week=1, lesson_duration_minutes=60, teaching_days=[0],
        holidays=[], ai_mode=AIMode.OFF,
        generation_method=GenerationMethod.ZELI,
    )


def _patch(monkeypatch, workers, fake_generate):
    import src.engines.generation_pipeline as gp
    import src.engines.generation_concurrency as gc

    monkeypatch.setattr(gp, "get_zeli_provider", lambda: FakeProvider())
    monkeypatch.setattr(gp, "get_zeli_fallback_provider", lambda: None)
    monkeypatch.setattr(gp, "generate_zeli_with_fallback", fake_generate)
    monkeypatch.setattr(
        gc, "effective_worker_count", lambda *a, **k: int(workers))


def _latency_provider(delay, tracker, fail_codes=()):
    lock = threading.Lock()

    def _generate(*, primary, fallback, context, db=None, user_id=None,
                  request_id=None):
        code = str(context.get("indicator_code") or "")
        with lock:
            tracker["active"] += 1
            tracker["peak"] = max(tracker["peak"], tracker["active"])
            tracker["started"].append(code)
        try:
            time.sleep(delay)
            if any(marker in code for marker in fail_codes):
                raise ZeliGenerationError(
                    "The provider could not generate this unit.", 502)
            return json.loads(json.dumps(_full_lesson(code))), {
                "provider": "groq", "model": "parallel-test-model",
                "attempts": [{"provider": "groq", "cache_hit": False}],
                "cache_hit": False, "external_calls": 1,
            }
        finally:
            with lock:
                tracker["active"] -= 1
                tracker["finished"].append(code)

    return _generate


def test_parallel_pool_is_bounded_and_keeps_curriculum_order(monkeypatch):
    tracker = {"active": 0, "peak": 0, "started": [], "finished": []}
    _patch(monkeypatch, 3, _latency_provider(0.12, tracker))

    job = GenerationPipeline().generate_all(_scheme(6), _config())

    assert job.status.value == "completed"
    assert len(job._lesson_plans) == 6
    assert tracker["peak"] == 3, tracker
    # Completion order may differ, the collection order may not.
    sequences = [lp.lesson_sequence for lp in job._lesson_plans]
    assert sequences == sorted(sequences)
    assert [lp.source_occurrence_id for lp in job._lesson_plans] == [
        lp.source_occurrence_id for lp in sorted(
            job._lesson_plans, key=lambda lp: lp.lesson_sequence)
    ]
    assert len({lp.id for lp in job._lesson_plans}) == 6
    assert getattr(job, "_generation_workers", 0) == 3
    assert len(getattr(job, "_lesson_timings", [])) == 6


def test_one_worker_is_sequential(monkeypatch):
    tracker = {"active": 0, "peak": 0, "started": [], "finished": []}
    _patch(monkeypatch, 1, _latency_provider(0.05, tracker))

    started = time.perf_counter()
    job = GenerationPipeline().generate_all(_scheme(4), _config())
    elapsed = time.perf_counter() - started

    assert tracker["peak"] == 1
    assert elapsed >= 4 * 0.05
    assert len(job._lesson_plans) == 4


def test_parallel_is_faster_than_sequential_for_provider_bound_work(monkeypatch):
    def _run(workers):
        tracker = {"active": 0, "peak": 0, "started": [], "finished": []}
        with pytest.MonkeyPatch.context() as mp:
            _patch(mp, workers, _latency_provider(0.08, tracker))
            started = time.perf_counter()
            job = GenerationPipeline().generate_all(_scheme(6), _config())
            return time.perf_counter() - started, job

    sequential, _ = _run(1)
    parallel, job = _run(3)
    assert len(job._lesson_plans) == 6
    # A 3-worker pool over six 80 ms calls must beat sequential clearly.
    assert parallel < sequential * 0.75, (sequential, parallel)


def test_one_failed_unit_keeps_the_others(monkeypatch):
    tracker = {"active": 0, "peak": 0, "started": [], "finished": []}
    _patch(monkeypatch, 3, _latency_provider(
        0.02, tracker, fail_codes=("B7.1.1.3.1",)))

    job = GenerationPipeline().generate_all(_scheme(6), _config())

    assert len(job._lesson_plans) == 5
    failed_codes = {
        item.get("indicator_code") for item in job._generation_failures
    }
    assert failed_codes == {"B7.1.1.3.1"}
    assert all(
        "B7.1.1.3.1" not in (lp.indicator_codes or [])
        for lp in job._lesson_plans
    )


def test_rate_limit_is_retried_without_duplicate_units(monkeypatch):
    calls = {"n": 0}
    seen = {}
    lock = threading.Lock()

    def _generate(*, primary, fallback, context, db=None, user_id=None,
                  request_id=None):
        code = str(context.get("indicator_code") or "")
        with lock:
            calls["n"] += 1
            seen[code] = seen.get(code, 0) + 1
            first = seen[code] == 1
        if first:
            raise ZeliGenerationError("Provider is busy. Try again.", 429)
        return json.loads(json.dumps(_full_lesson())), {
            "provider": "groq", "model": "parallel-test-model",
            "attempts": [{"provider": "groq", "cache_hit": False}],
            "cache_hit": False, "external_calls": 1,
        }

    _patch(monkeypatch, 2, _generate)
    job = GenerationPipeline().generate_all(_scheme(2), _config())

    assert len(job._lesson_plans) == 2
    assert len({lp.source_occurrence_id for lp in job._lesson_plans}) == 2
    assert calls["n"] == 4  # one refusal + one success per unit
    timings = getattr(job, "_lesson_timings", [])
    assert all(t.get("retry_count") == 1 for t in timings), timings


def test_progress_callback_receives_each_unit_once(monkeypatch):
    tracker = {"active": 0, "peak": 0, "started": [], "finished": []}
    _patch(monkeypatch, 2, _latency_provider(0.02, tracker))
    events = []
    lock = threading.Lock()

    def _progress(event):
        with lock:
            events.append(event)

    job = GenerationPipeline().generate_all(
        _scheme(5), _config(), unit_progress=_progress)

    assert len(job._lesson_plans) == 5
    assert len(events) == 5
    assert len({e["source_occurrence_id"] for e in events}) == 5
    assert all(e["success"] for e in events)


def test_unknown_worker_setting_stays_within_provider_ceiling():
    from src.engines.generation_concurrency import (
        effective_worker_count, provider_concurrency_limit,
    )

    assert provider_concurrency_limit("gemini") == 1
    assert provider_concurrency_limit("groq") == 3
    assert effective_worker_count(8, "gemini", ai_limit=8) == 1
    assert effective_worker_count(8, "groq", ai_limit=2) == 2
    assert effective_worker_count(1, "groq", ai_limit=8) == 1


def test_concurrency_setting_is_bounded():
    from src.config import Settings

    assert Settings(GENERATION_MAX_CONCURRENCY=1).GENERATION_MAX_CONCURRENCY == 1
    assert Settings(GENERATION_MAX_CONCURRENCY=4).GENERATION_MAX_CONCURRENCY == 4
    with pytest.raises(ValueError):
        Settings(GENERATION_MAX_CONCURRENCY=0)
    with pytest.raises(ValueError):
        Settings(GENERATION_MAX_CONCURRENCY=9)


def test_progress_callback_marks_generated_but_not_completed(db):
    """Live progress may say generated; only persistence may say completed."""
    from src.database import GenerationJobDB, SchemeDB
    from src.routers.generation import _unit_progress_callback
    from tests.conftest import make_user

    user = make_user(db)
    scheme = SchemeDB(
        id="progress-scheme", owner_id=user.id, filename="p.docx",
        subject="Mathematics", class_level="Basic 4",
    )
    job = GenerationJobDB(
        id="progress-job", owner_id=user.id, scheme_id=scheme.id,
        status="processing",
        config_snapshot={"lesson_units": [
            {"source_occurrence_id": "week1:0:B4.1.1.1.1", "state": "processing"},
            {"source_occurrence_id": "week2:0:B4.1.1.2.1", "state": "processing"},
        ]},
    )
    db.add_all([scheme, job])
    db.commit()

    callback = _unit_progress_callback(
        job.id, user.id, db.get_bind())
    callback({
        "source_occurrence_id": "week1:0:B4.1.1.1.1",
        "success": True,
        "duration_seconds": 0.25,
    })

    db.expire_all()
    updated = db.query(GenerationJobDB).filter(
        GenerationJobDB.id == job.id).one()
    units = updated.config_snapshot["lesson_units"]
    first = next(
        u for u in units if u["source_occurrence_id"] == "week1:0:B4.1.1.1.1")
    assert first["state"] == "generated"
    assert first["last_duration_seconds"] == 0.25
    # Not counted as complete before the result is persisted.
    assert updated.completed_lessons == 0
    assert updated.config_snapshot["generated_units"] == 1


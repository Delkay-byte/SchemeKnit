"""Global and per-teacher provider concurrency limits across parent jobs.

The worker pool is per parent job. These tests prove that the SHARED database
permits, not the pool, are the authority when jobs overlap:

* provider-wide ceiling across different teachers;
* per-teacher ceiling across two of that teacher's jobs;
* process-global ceiling;
* permits are released on success/failure and expire after a crash.
"""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src import ai_spend
from src.database import Base


def _set(monkeypatch, **values):
    for key, value in values.items():
        monkeypatch.setenv(key, str(value))
    from src.config import get_settings
    get_settings.cache_clear()


def _attempt(db, user="teacher-1", provider="deepseek", request="r"):
    return ai_spend.begin_attempt(
        db, provider=provider, model="deepseek-flash",
        prompt_chars=1000, user_id=user, request_id=request)


def test_provider_ceiling_is_shared_across_teachers(db, monkeypatch):
    _set(monkeypatch, AI_MAX_CONCURRENT_PER_TEACHER=8,
         AI_GLOBAL_MAX_CONCURRENT=8,
         GENERATION_PROVIDER_CONCURRENCY="deepseek=1")

    first = _attempt(db, user="teacher-a", request="a")
    with pytest.raises(ai_spend.AISpendConcurrencyExceeded):
        _attempt(db, user="teacher-b", request="b")
    first.finish("success", usage={"input_tokens": 10, "output_tokens": 5})
    second = _attempt(db, user="teacher-b", request="c")
    second.finish("success", usage={"input_tokens": 10, "output_tokens": 5})


def test_per_teacher_ceiling_spans_two_parent_jobs(db, monkeypatch):
    _set(monkeypatch, AI_MAX_CONCURRENT_PER_TEACHER=1,
         AI_GLOBAL_MAX_CONCURRENT=8,
         GENERATION_PROVIDER_CONCURRENCY="deepseek=8")

    job_a = _attempt(db, user="teacher-1", request="job-a")
    with pytest.raises(ai_spend.AISpendConcurrencyExceeded):
        _attempt(db, user="teacher-1", request="job-b")
    # A different teacher is not blocked by teacher-1's job.
    other = _attempt(db, user="teacher-2", request="job-c")
    job_a.finish("success", usage={"input_tokens": 10, "output_tokens": 5})
    job_b = _attempt(db, user="teacher-1", request="job-b2")
    other.finish("success", usage={"input_tokens": 10, "output_tokens": 5})
    job_b.finish("success", usage={"input_tokens": 10, "output_tokens": 5})


def test_process_global_ceiling_is_shared(db, monkeypatch):
    _set(monkeypatch, AI_MAX_CONCURRENT_PER_TEACHER=8,
         AI_GLOBAL_MAX_CONCURRENT=1,
         GENERATION_PROVIDER_CONCURRENCY="deepseek=8")

    first = _attempt(db, user="teacher-a", request="a")
    with pytest.raises(ai_spend.AISpendConcurrencyExceeded):
        _attempt(db, user="teacher-b", request="b")
    first.finish("success", usage={"input_tokens": 10, "output_tokens": 5})


def test_failed_attempt_releases_every_permit(db, monkeypatch):
    _set(monkeypatch, AI_MAX_CONCURRENT_PER_TEACHER=1,
         AI_GLOBAL_MAX_CONCURRENT=1,
         GENERATION_PROVIDER_CONCURRENCY="deepseek=1")

    first = _attempt(db, user="teacher-1", request="a")
    first.finish("failure", error_code="timeout")
    again = _attempt(db, user="teacher-1", request="b")
    again.finish("success", usage={"input_tokens": 10, "output_tokens": 5})


def test_expired_lease_cannot_block_future_generation(db, monkeypatch):
    _set(monkeypatch, AI_MAX_CONCURRENT_PER_TEACHER=1,
         AI_GLOBAL_MAX_CONCURRENT=1,
         GENERATION_PROVIDER_CONCURRENCY="deepseek=1")

    # Simulate a crashed process that never called finish().
    _attempt(db, user="teacher-1", request="crashed")
    db.execute(text(
        "UPDATE ai_spend_counters SET expires_at = :past "
        "WHERE scope IN ('concurrency_global','concurrency_user',"
        "'concurrency_provider')"
    ), {"past": datetime.utcnow() - timedelta(minutes=10)})
    db.commit()

    recovered = _attempt(db, user="teacher-2", request="after-crash")
    recovered.finish("success", usage={"input_tokens": 10, "output_tokens": 5})


def test_two_sessions_cannot_both_take_the_last_provider_permit(
        tmp_path, monkeypatch):
    _set(monkeypatch, AI_MAX_CONCURRENT_PER_TEACHER=8,
         AI_GLOBAL_MAX_CONCURRENT=8,
         GENERATION_PROVIDER_CONCURRENCY="deepseek=1")
    engine = create_engine(
        f"sqlite:///{tmp_path / 'permits.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    barrier = threading.Barrier(2)
    results = []
    lock = threading.Lock()

    def _worker(user):
        db = Session()
        try:
            barrier.wait(timeout=5)
            attempt = None
            for _ in range(50):
                try:
                    attempt = _attempt(db, user=user, request=user)
                    break
                except ai_spend.AISpendConcurrencyExceeded:
                    raise
                except ai_spend.AISpendError:
                    # SQLite may serialise the first insert; retry the lock
                    # before asserting the provider permit count.
                    db.rollback()
                    time.sleep(0.1)
            if attempt is None:
                raise AssertionError("permit attempt did not settle")
            with lock:
                results.append("acquired")
            time.sleep(0.2)
            attempt.finish(
                "success", usage={"input_tokens": 10, "output_tokens": 5})
        except ai_spend.AISpendConcurrencyExceeded:
            with lock:
                results.append("limited")
        finally:
            db.close()

    threads = [
        threading.Thread(target=_worker, args=(f"teacher-{i}",))
        for i in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert sorted(results) == ["acquired", "limited"], results
    engine.dispose()


def test_worker_queues_for_a_shared_permit_instead_of_failing(monkeypatch):
    """A blocked permit is waited on, then the same lesson retries."""
    import src.engines.generation_pipeline as gp
    from src.models import (
        AIMode, ClassLevel, GenerationMethod, SchemeOfWork, Subject,
        TermConfig, Week, WeekType,
    )
    from datetime import date

    calls = {"n": 0}

    class _Provider:
        model = "test"
        name = "deepseek"

        def get_name(self):
            return self.name

    def _generate(*, primary, fallback, context, db=None, user_id=None,
                  request_id=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise gp.ZeliGenerationError(
                "Another AI generation is already running.",
                429, code="ai_concurrency_limited")
        return {
            "learning_objectives": ["Learners can name a device."],
            "starter": {"activity": "Teacher shows a device."},
            "main_learning": {
                "phase1": {"activity": "Learners sort devices.",
                           "duration_minutes": 20},
                "phase2": {"activity": "Pairs label a chart.",
                           "duration_minutes": 20},
            },
            "assessment": {"method": "Observation",
                           "activity": "Teacher checks the chart."},
            "plenary": {"activity": "Learners state one use."},
        }, {"provider": "deepseek", "model": "test", "attempts": [],
            "cache_hit": False, "external_calls": 1}

    class _Settings:
        GENERATION_CONCURRENCY_WAIT_SECONDS = 5
        GENERATION_MAX_CONCURRENCY = 3

    monkeypatch.setattr(gp, "get_zeli_provider", lambda: _Provider())
    monkeypatch.setattr(gp, "get_zeli_fallback_provider", lambda: None)
    monkeypatch.setattr(gp, "generate_zeli_with_fallback", _generate)
    import src.engines.generation_concurrency as gc
    monkeypatch.setattr(gc, "effective_worker_count", lambda *a, **k: 1)
    monkeypatch.setattr(
        "src.config.get_settings", lambda: _Settings())

    week = Week(
        week_number=1, start_date=date(2026, 9, 7),
        end_date=date(2026, 9, 11), week_type=WeekType.INSTRUCTION,
        strand="Computing", sub_strand="Hardware",
        content_standards=["B7.1.1.1"],
        indicators=["B7.1.1.1.1 Identify a device"],
        resources=["Chart"], scheme_of_work_id="queue",
    )
    scheme = SchemeOfWork(
        id="queue", filename="q.docx", class_level=ClassLevel.BASIC_7,
        subject=Subject.ICT, term="First Term", academic_year="2026/2027",
        weeks=[week], upload_date=date(2026, 9, 1),
    )
    config = TermConfig(
        scheme_of_work_id="queue", academic_year="2026/2027",
        term="First Term", class_level="Basic 7", subject="ICT",
        term_start_date=date(2026, 9, 7), term_end_date=date(2026, 12, 18),
        lessons_per_week=1, lesson_duration_minutes=60, teaching_days=[0],
        holidays=[], ai_mode=AIMode.OFF,
        generation_method=GenerationMethod.ZELI,
    )
    job = gp.GenerationPipeline().generate_all(scheme, config)

    assert calls["n"] == 2
    assert len(job._lesson_plans) == 1
    assert job._lesson_timings[0]["retry_count"] == 1

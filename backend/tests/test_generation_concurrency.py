"""Truly concurrent /generate requests for the same scheme.

Production runs a single uvicorn process (`src.main:app`). Two teacher clicks
(or a double-submit that passes the pre-check before either job is visible)
must NOT start two competing runs: the second must be refused with 409 and
must not reserve or charge quota.

The route is deliberately synchronous so FastAPI serves it from its
threadpool; concurrent requests are real threads, not an event-loop
serialization. A process-wide per-(user, scheme) lock makes the guard
non-blocking; the DB in-flight check remains the cross-process fallback.

This test drives two real HTTP requests in parallel threads with separate
sessions (the production arrangement). Under PostgreSQL it runs on the
production driver when ``TEACHFLOW_TEST_DATABASE_URL`` is set.
"""

from __future__ import annotations

import hashlib
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(autouse=True)
def _wide_free_allowance(monkeypatch):
    """Concurrency mechanics use a 3-lesson run; the approved 2-credit policy
    is pinned separately."""
    from src import entitlements
    monkeypatch.setattr(entitlements, "FREE_TIER_LESSON_PLANS_PER_MONTH", 10)

from src.database import (  # noqa: E402
    Base, GenerationJobDB, LessonPlanDB, SchemeDB, UsagePeriodDB, UsageUnitDB,
    WeekDB, generate_id,
)
from src.usage_quota import current_period_key  # noqa: E402
from tests.conftest import make_user  # noqa: E402


@pytest.fixture
def concurrent_engine(db_engine, tmp_path):
    """A database safe for two threads.

    PostgreSQL: the conftest engine (real production arrangement).
    SQLite: a file database with a connection per thread; the in-memory
    StaticPool engine is a single shared connection and cannot model two
    concurrent request sessions.
    """
    url = os.environ.get("TEACHFLOW_TEST_DATABASE_URL", "")
    if url.startswith("postgresql"):
        yield db_engine
        return
    engine = create_engine(
        f"sqlite:///{tmp_path / 'concurrency.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


def _app(session_factory, user):
    from fastapi import FastAPI
    from src.auth import get_current_user, require_teacher_workflow
    from src.database import get_db
    from src.routers import generation as gen_router

    def _db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app = FastAPI()
    app.include_router(gen_router.router, prefix="/api/generation")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_teacher_workflow] = lambda: user
    app.dependency_overrides[get_db] = _db
    return app


def _config(scheme_id):
    from src.models import TermConfig

    return TermConfig(
        scheme_of_work_id=scheme_id,
        term_start_date=date(2026, 9, 7), term_end_date=date(2026, 12, 18),
        lessons_per_week=3, lesson_duration_minutes=60, class_size=30,
        teaching_days=[0, 2, 4], holidays=[], ai_mode="OFF",
        include_special_weeks=False, class_level="Basic 7", subject="ICT",
    )


def test_two_concurrent_generate_requests_start_exactly_one_run(
        concurrent_engine, tmp_path):
    from src import service as service_module

    Session = sessionmaker(bind=concurrent_engine)
    setup = Session()
    try:
        user = make_user(setup)
        scheme = SchemeDB(id=generate_id(), owner_id=user.id,
                          filename="s.docx", subject="ICT",
                          class_level="Basic 7")
        setup.add(scheme)
        setup.flush()
        for n in (1, 2, 3):
            setup.add(WeekDB(
                id=generate_id(), scheme_id=scheme.id, week_number=n,
                start_date=date(2026, 9, 7), end_date=date(2026, 9, 11),
                week_type="instruction", strand="Computing",
                sub_strand="Hardware",
                content_standards=[f"B7.1.1.{n}"],
                indicators=[f"B7.1.1.{n}.1 Identify a device"],
                resources=["Chart"],
            ))
        setup.commit()
        user_id, scheme_id = user.id, scheme.id
    finally:
        setup.close()

    # Force BOTH requests past the in-flight read before either creates its
    # job. Without a process lock both would then start a run; the barrier
    # removes timing luck from the race.
    arrived = threading.Barrier(2)
    original_list_jobs = service_module.data_service.list_jobs

    def gated_list_jobs(db, owner_id):
        try:
            arrived.wait(timeout=2)
        except threading.BrokenBarrierError:
            pass
        return original_list_jobs(db, owner_id)

    app = _app(Session, user)
    config = _config(scheme_id).model_dump(mode="json")

    def submit(_):
        with TestClient(app) as client:
            return client.post(
                f"/api/generation/{scheme_id}/generate", json=config)

    from unittest.mock import patch
    with patch.object(service_module.data_service, "list_jobs",
                      side_effect=gated_list_jobs):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, range(2)))

    statuses = sorted(r.status_code for r in results)
    assert statuses == [200, 409], (
        "exactly one concurrent request may run; got "
        f"{[(r.status_code, r.text[:120]) for r in results]}")

    check = Session()
    try:
        jobs = (
            check.query(GenerationJobDB)
            .filter(GenerationJobDB.owner_id == user_id,
                    GenerationJobDB.scheme_id == scheme_id)
            .count()
        )
        units = (
            check.query(UsageUnitDB)
            .filter(UsageUnitDB.user_id == user_id,
                    UsageUnitDB.period_key == current_period_key())
            .count()
        )
        period = (
            check.query(UsagePeriodDB)
            .filter(UsagePeriodDB.user_id == user_id,
                    UsagePeriodDB.period_key == current_period_key())
            .first()
        )
        lessons = (
            check.query(LessonPlanDB)
            .filter(LessonPlanDB.owner_id == user_id,
                    LessonPlanDB.scheme_id == scheme_id)
            .count()
        )
    finally:
        check.close()

    assert jobs == 1, "the refused request must not create a second job"
    assert lessons > 0
    assert units == 3, "one unit per indicator code, never double-charged"
    assert int(period.units_used or 0) == 3


def _generation_lock_key(user_id: str, scheme_id: str) -> int:
    """Contract for the database-level generation lock key.

    The guard must be cross-process, so an external PostgreSQL session holding
    this key must block the endpoint even when the in-process threading lock is
    free. Keep this derivation in sync with the router.
    """
    digest = hashlib.sha256(
        f"schemeknit:generation:{user_id}:{scheme_id}".encode("utf-8")
    ).digest()[:8]
    return int.from_bytes(digest, "big", signed=True)


@pytest.mark.skipif(
    not os.environ.get("TEACHFLOW_TEST_DATABASE_URL", "").startswith("postgresql"),
    reason="advisory-lock behavior is meaningful only on PostgreSQL",
)
def test_postgres_advisory_lock_blocks_a_second_connection(
        concurrent_engine, tmp_path):
    """An external PostgreSQL session must block generate before any work."""
    from src.database import GenerationJobDB, LessonPlanDB, SchemeDB, WeekDB, generate_id
    from src.usage_quota import current_period_key

    Session = sessionmaker(bind=concurrent_engine)
    setup = Session()
    try:
        user = make_user(setup)
        scheme = SchemeDB(id=generate_id(), owner_id=user.id,
                          filename="s.docx", subject="ICT",
                          class_level="Basic 7")
        setup.add(scheme)
        setup.flush()
        for n in (1, 2, 3):
            setup.add(WeekDB(
                id=generate_id(), scheme_id=scheme.id, week_number=n,
                start_date=date(2026, 9, 7), end_date=date(2026, 9, 11),
                week_type="instruction", strand="Computing",
                sub_strand="Hardware",
                content_standards=[f"B7.1.1.{n}"],
                indicators=[f"B7.1.1.{n}.1 Identify a device"],
                resources=["Chart"],
            ))
        setup.commit()
        user_id, scheme_id = user.id, scheme.id
    finally:
        setup.close()

    app = _app(Session, user)
    config = _config(scheme_id).model_dump(mode="json")
    key = _generation_lock_key(user_id, scheme_id)

    blocker = concurrent_engine.connect()
    try:
        assert blocker.execute(
            text("SELECT pg_try_advisory_lock(:k)"), {"k": key}
        ).scalar() is True

        with TestClient(app) as client:
            blocked = client.post(
                f"/api/generation/{scheme_id}/generate", json=config)

        assert blocked.status_code == 409, (
            "an externally held database lock must refuse the run; got "
            f"{blocked.status_code} {blocked.text[:160]}")

        check = Session()
        try:
            assert check.query(GenerationJobDB).filter(
                GenerationJobDB.owner_id == user_id,
                GenerationJobDB.scheme_id == scheme_id,
            ).count() == 0, "a refused run must not create a job"
        finally:
            check.close()
    finally:
        blocker.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
        blocker.commit()
        blocker.close()

    with TestClient(app) as client:
        allowed = client.post(
            f"/api/generation/{scheme_id}/generate", json=config)

    assert allowed.status_code == 200, allowed.text
    check = Session()
    try:
        jobs = check.query(GenerationJobDB).filter(
            GenerationJobDB.owner_id == user_id,
            GenerationJobDB.scheme_id == scheme_id,
        ).count()
        lessons = check.query(LessonPlanDB).filter(
            LessonPlanDB.owner_id == user_id,
            LessonPlanDB.scheme_id == scheme_id,
        ).count()
    finally:
        check.close()
    assert jobs == 1
    assert lessons > 0
    assert current_period_key()  # sanity: the period is server-derived

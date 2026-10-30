"""Phase 5 — crash recovery: orphaned generation jobs fail at startup.

A hard process death mid-generation (SIGKILL, OOM, deploy restart) skips the
generate endpoint's exception handlers, so the job row would stay ``pending``
forever — shadowing the scheme status endpoint and the job history. The
startup reconciliation sweep (DataService.reconcile_stale_generation_jobs,
wired into the app lifespan) must fail such orphans, and only orphans:
recent non-terminal jobs and terminal jobs stay untouched.
"""

import os
import sys
import time
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.conftest import make_user, make_school
from src.database import SchemeDB, GenerationJobDB, generate_id
from src.service import data_service


@pytest.fixture()
def teacher_scheme(db):
    school = make_school(db)
    teacher = make_user(db, role="teacher", school_id=school.id,
                        email="crash@rec.test")
    scheme = SchemeDB(id=generate_id(), owner_id=teacher.id, school_id=school.id,
                      filename="s.docx", subject="Science", class_level="Basic 9",
                      status="approved")
    db.add(scheme)
    db.commit()
    return teacher, scheme


def _job(db, teacher, scheme, status, age_minutes, heartbeat_age_minutes=None,
         now=None):
    now = now or datetime.utcnow()
    job = GenerationJobDB(
        id=generate_id(), owner_id=teacher.id, scheme_id=scheme.id,
        status=status,
        created_at=now - timedelta(minutes=age_minutes),
        heartbeat_at=(
            None if heartbeat_age_minutes is None
            else now - timedelta(minutes=heartbeat_age_minutes)
        ),
    )
    db.add(job)
    db.commit()
    return job


def test_stale_pending_job_is_failed(db, teacher_scheme):
    teacher, scheme = teacher_scheme
    job = _job(db, teacher, scheme, "pending", age_minutes=120)

    assert data_service.reconcile_stale_generation_jobs(db) == 1

    db.refresh(job)
    assert job.status == "failed"
    assert "interrupted by a server restart" in job.error_message
    assert job.completed_at is not None


def test_recent_pending_and_terminal_jobs_untouched(db, teacher_scheme):
    teacher, scheme = teacher_scheme
    recent = _job(db, teacher, scheme, "pending", age_minutes=2)
    done = _job(db, teacher, scheme, "completed", age_minutes=500)
    dead = _job(db, teacher, scheme, "failed", age_minutes=500)
    old_processing = _job(db, teacher, scheme, "processing", age_minutes=90)

    assert data_service.reconcile_stale_generation_jobs(db) == 1

    db.refresh(recent)
    db.refresh(done)
    db.refresh(dead)
    db.refresh(old_processing)
    assert recent.status == "pending"
    assert done.status == "completed"
    assert dead.status == "failed"
    assert old_processing.status == "failed"


def test_reconcile_does_not_touch_lessons_or_quota(db, teacher_scheme):
    from src.database import LessonPlanDB
    teacher, scheme = teacher_scheme
    job = _job(db, teacher, scheme, "pending", age_minutes=180)
    lp = LessonPlanDB(
        id=generate_id(), job_id=job.id, owner_id=teacher.id,
        scheme_id=scheme.id, week_number=1, lesson_sequence=1,
        class_level="Basic 9", subject="Science")
    db.add(lp)
    db.commit()

    assert data_service.reconcile_stale_generation_jobs(db) == 1

    remaining = db.query(LessonPlanDB).filter_by(job_id=job.id).all()
    assert [r.id for r in remaining] == [lp.id]


# ── Boundary and heartbeat policy (deterministic clock) ──────────────────────
# The policy is: a non-terminal job is orphaned only when its last activity
# (heartbeat_at, else created_at) is STRICTLY older than the configured stale
# duration. Exactly at the threshold is still allowed to run. A healthy
# heartbeat keeps a long-running job out of recovery.

_FIXED_NOW = datetime(2026, 10, 28, 12, 0, 0)


def test_job_exactly_at_the_threshold_is_not_stale(db, teacher_scheme):
    teacher, scheme = teacher_scheme
    job = _job(db, teacher, scheme, "processing", age_minutes=60, now=_FIXED_NOW)

    assert data_service.reconcile_stale_generation_jobs(
        db, older_than_minutes=60, now=_FIXED_NOW) == 0
    db.refresh(job)
    assert job.status == "processing"


def test_job_one_second_past_the_threshold_is_stale(db, teacher_scheme):
    teacher, scheme = teacher_scheme
    job = _job(db, teacher, scheme, "processing", age_minutes=60, now=_FIXED_NOW)
    job.created_at = _FIXED_NOW - timedelta(minutes=60, seconds=1)
    db.commit()

    assert data_service.reconcile_stale_generation_jobs(
        db, older_than_minutes=60, now=_FIXED_NOW) == 1
    db.refresh(job)
    assert job.status == "failed"


def test_heartbeat_keeps_a_long_running_job_alive(db, teacher_scheme):
    """Created 3 hours ago but active 10 seconds ago: not orphaned."""
    teacher, scheme = teacher_scheme
    job = _job(
        db, teacher, scheme, "processing", age_minutes=180,
        heartbeat_age_minutes=0, now=_FIXED_NOW,
    )
    job.heartbeat_at = _FIXED_NOW - timedelta(seconds=10)
    db.commit()

    assert data_service.reconcile_stale_generation_jobs(
        db, older_than_minutes=60, now=_FIXED_NOW) == 0
    db.refresh(job)
    assert job.status == "processing"


def test_heartbeat_older_than_threshold_is_stale(db, teacher_scheme):
    teacher, scheme = teacher_scheme
    job = _job(
        db, teacher, scheme, "processing", age_minutes=180,
        heartbeat_age_minutes=61, now=_FIXED_NOW,
    )

    assert data_service.reconcile_stale_generation_jobs(
        db, older_than_minutes=60, now=_FIXED_NOW) == 1
    db.refresh(job)
    assert job.status == "failed"


def test_heartbeat_takes_precedence_over_created_at(db, teacher_scheme):
    """A recent heartbeat protects even a very old job; the opposite too."""
    teacher, scheme = teacher_scheme
    old_but_active = _job(
        db, teacher, scheme, "processing", age_minutes=600,
        heartbeat_age_minutes=2, now=_FIXED_NOW,
    )
    recent_but_stalled = _job(
        db, teacher, scheme, "processing", age_minutes=5,
        heartbeat_age_minutes=120, now=_FIXED_NOW,
    )

    assert data_service.reconcile_stale_generation_jobs(
        db, older_than_minutes=60, now=_FIXED_NOW) == 1
    db.refresh(old_but_active)
    db.refresh(recent_but_stalled)
    assert old_but_active.status == "processing"
    assert recent_but_stalled.status == "failed"


def test_heartbeat_job_only_updates_live_jobs(db, teacher_scheme):
    teacher, scheme = teacher_scheme
    live = _job(db, teacher, scheme, "processing", age_minutes=10)
    done = _job(db, teacher, scheme, "completed", age_minutes=10)

    assert data_service.heartbeat_job(db, live.id, at=_FIXED_NOW) is True
    assert data_service.heartbeat_job(db, done.id, at=_FIXED_NOW) is False

    db.refresh(live)
    db.refresh(done)
    assert live.heartbeat_at == _FIXED_NOW
    assert done.heartbeat_at is None


def test_reconcile_uses_configured_stale_duration(db, teacher_scheme, monkeypatch):
    """The default is configurable, not a hard-coded 60-minute constant."""
    from types import SimpleNamespace
    import src.service as service_module

    teacher, scheme = teacher_scheme
    job = _job(db, teacher, scheme, "processing", age_minutes=10, now=_FIXED_NOW)
    monkeypatch.setattr(
        service_module, "get_settings",
        lambda: SimpleNamespace(GENERATION_STALE_MINUTES=5),
    )

    assert data_service.reconcile_stale_generation_jobs(
        db, now=_FIXED_NOW) == 1
    db.refresh(job)
    assert job.status == "failed"


def test_a_running_job_is_heartbeated_while_work_continues(
        db, db_engine, teacher_scheme, monkeypatch):
    """The worker lease is real: a long run keeps proving it is alive."""
    from types import SimpleNamespace
    from sqlalchemy.orm import sessionmaker
    from src.routers import generation as gen_router

    teacher, scheme = teacher_scheme
    job = _job(db, teacher, scheme, "processing", age_minutes=10)
    old = datetime.utcnow() - timedelta(minutes=10)
    job.heartbeat_at = old
    db.commit()

    monkeypatch.setattr(
        gen_router, "SessionLocal", sessionmaker(bind=db_engine))
    monkeypatch.setattr(
        gen_router, "get_settings",
        lambda: SimpleNamespace(GENERATION_HEARTBEAT_SECONDS=1),
    )

    with gen_router._job_heartbeat(job.id):
        time.sleep(1.4)

    db.expire_all()
    db.refresh(job)
    assert job.heartbeat_at is not None
    assert job.heartbeat_at > old, (
        "the heartbeat thread did not refresh a live job")

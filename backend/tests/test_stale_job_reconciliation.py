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


def _job(db, teacher, scheme, status, age_minutes):
    job = GenerationJobDB(
        id=generate_id(), owner_id=teacher.id, scheme_id=scheme.id,
        status=status,
        created_at=datetime.utcnow() - timedelta(minutes=age_minutes))
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

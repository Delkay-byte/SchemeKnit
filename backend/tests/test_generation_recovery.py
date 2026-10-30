"""Recovery from generation jobs orphaned by a hard process death.

A deploy restart, OOM kill or SIGKILL skips the endpoint's exception handlers,
so the job row stays ``pending`` forever. The next generate click must not be
blocked by that stale row, and the status poll must report a terminal state so
the UI can offer a retry instead of spinning indefinitely.
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(autouse=True)
def _wide_free_allowance(monkeypatch):
    """Recovery mechanics use a 3-lesson run; see test_commercial_model for
    the approved 2-credit policy."""
    from src import entitlements
    monkeypatch.setattr(entitlements, "FREE_TIER_LESSON_PLANS_PER_MONTH", 10)

from src.database import (  # noqa: E402
    GenerationJobDB, LessonPlanDB, SchemeDB, WeekDB, generate_id,
)
from tests.conftest import make_user  # noqa: E402


def _scheme(db, owner_id):
    scheme = SchemeDB(id=generate_id(), owner_id=owner_id, filename="s.docx",
                      subject="ICT", class_level="Basic 7")
    db.add(scheme)
    db.flush()
    for n in (1, 2, 3):
        db.add(WeekDB(
            id=generate_id(), scheme_id=scheme.id, week_number=n,
            start_date=date(2026, 9, 7), end_date=date(2026, 9, 11),
            week_type="instruction", strand="Computing",
            sub_strand="Hardware",
            content_standards=[f"B7.1.1.{n}"],
            indicators=[f"B7.1.1.{n}.1 Identify a device"],
            resources=["Chart"],
        ))
    db.commit()
    return scheme


def _stale_job(db, owner_id, scheme_id, status="pending"):
    job = GenerationJobDB(
        id=generate_id(), owner_id=owner_id, scheme_id=scheme_id,
        status=status,
        created_at=datetime.utcnow() - timedelta(hours=2),
    )
    db.add(job)
    db.commit()
    return job


def _config(scheme_id):
    from src.models import TermConfig

    return TermConfig(
        scheme_of_work_id=scheme_id,
        term_start_date=date(2026, 9, 7), term_end_date=date(2026, 12, 18),
        lessons_per_week=3, lesson_duration_minutes=60, class_size=30,
        teaching_days=[0, 2, 4], holidays=[], ai_mode="OFF",
        include_special_weeks=False, class_level="Basic 7", subject="ICT",
    )


def _app(db, user):
    from fastapi import FastAPI
    from src.auth import get_current_user, require_teacher_workflow
    from src.database import get_db
    from src.routers import generation as gen_router

    app = FastAPI()
    app.include_router(gen_router.router, prefix="/api/generation")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_teacher_workflow] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    return app


def test_generate_reclaims_a_stale_pending_job_and_runs(db):
    user = make_user(db)
    scheme = _scheme(db, user.id)
    stale = _stale_job(db, user.id, scheme.id)

    with TestClient(_app(db, user)) as client:
        resp = client.post(
            f"/api/generation/{scheme.id}/generate",
            json=_config(scheme.id).model_dump(mode="json"),
        )

    assert resp.status_code == 200, resp.text
    db.expire_all()
    db.refresh(stale)
    assert stale.status == "failed"
    assert "interrupted" in (stale.error_message or "").lower()
    assert db.query(LessonPlanDB).filter(
        LessonPlanDB.scheme_id == scheme.id).count() > 0


def test_status_poll_reports_a_stale_pending_job_as_failed(db):
    user = make_user(db)
    scheme = _scheme(db, user.id)
    stale = _stale_job(db, user.id, scheme.id, status="processing")

    with TestClient(_app(db, user)) as client:
        resp = client.get(f"/api/generation/{stale.id}/status")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "failed"
    assert "interrupted" in (body["error_message"] or "").lower()


def test_scheme_status_reclaims_a_stale_job_on_page_reload(db):
    """The generate page restores from /scheme/{id}/status, not /{id}/status.

    A reload after a server restart must therefore reclaim the orphaned row
    there as well; otherwise the failure banner never appears and the teacher
    is told nothing until they click Generate again.
    """
    user = make_user(db)
    scheme = _scheme(db, user.id)
    stale = _stale_job(db, user.id, scheme.id, status="processing")

    with TestClient(_app(db, user)) as client:
        resp = client.get(f"/api/generation/scheme/{scheme.id}/status")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == stale.id
    assert body["status"] == "failed"
    assert "interrupted" in (body["error_message"] or "").lower()


def test_a_recent_pending_job_still_blocks_a_second_run(db):
    """The reclamation must not fail a live run (age threshold)."""
    user = make_user(db)
    scheme = _scheme(db, user.id)
    live = GenerationJobDB(id=generate_id(), owner_id=user.id,
                           scheme_id=scheme.id, status="processing")
    db.add(live)
    db.commit()

    with TestClient(_app(db, user)) as client:
        resp = client.post(
            f"/api/generation/{scheme.id}/generate",
            json=_config(scheme.id).model_dump(mode="json"),
        )

    assert resp.status_code == 409, resp.text
    db.refresh(live)
    assert live.status == "processing"

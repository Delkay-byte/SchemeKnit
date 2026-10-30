"""True resume of a partial generation batch.

A retry that re-plans the whole scheme is not a recovery operation. These tests
pin the properties that make resume different:

* the SAME job row is reused (its AI-credit idempotency is preserved);
* only the originally planned, not-yet-persisted occurrences run;
* lessons that already exist are never duplicated or deleted;
* quota is charged once per indicator code, not once per resume click;
* a late failure during resume is all-or-nothing for the resumed lessons;
* a resume that cannot fit the remaining allowance performs no work.
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.database import (  # noqa: E402
    GenerationJobDB, LessonPlanDB, SchemeDB, UsagePeriodDB, UsageUnitDB,
    WeekDB, generate_id,
)
from src.engines.generation_pipeline import GenerationPipeline  # noqa: E402
from src.usage_quota import current_period_key  # noqa: E402
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


def _allocations(scheme_db, config):
    from src.service import data_service

    pipeline = GenerationPipeline()
    scheme = data_service.scheme_to_model(scheme_db)
    calendar = pipeline.calendar_engine.build_calendar(
        config, scheme.weeks, config.holidays)
    coverage = pipeline.allocation_engine.allocate(
        scheme.weeks, calendar, config, config.include_special_weeks)
    return [a for a in coverage.allocations if a.source_occurrence_id]


def _generate_first(scheme, alloc):
    from src.models import TermConfig

    config = _config(scheme.id)
    config.selected_occurrence_ids = [alloc.source_occurrence_id]
    config.selected_indicator_codes = [alloc.indicator_code]
    return config


def _state(db, user, scheme):
    db.expire_all()
    period_key = current_period_key()
    lessons = db.query(LessonPlanDB).filter(
        LessonPlanDB.owner_id == user.id,
        LessonPlanDB.scheme_id == scheme.id,
    ).order_by(LessonPlanDB.created_at).all()
    units = db.query(UsageUnitDB).filter(
        UsageUnitDB.user_id == user.id,
        UsageUnitDB.period_key == period_key,
    ).all()
    period = db.query(UsagePeriodDB).filter(
        UsagePeriodDB.user_id == user.id,
        UsagePeriodDB.period_key == period_key,
    ).first()
    job = db.query(GenerationJobDB).filter(
        GenerationJobDB.owner_id == user.id,
        GenerationJobDB.scheme_id == scheme.id,
    ).order_by(GenerationJobDB.created_at.desc()).first()
    return {
        "lessons": lessons,
        "units": units,
        "units_used": int(period.units_used or 0) if period else 0,
        "job": job,
    }


def _partial_job(db, user, scheme, allocations):
    """One persisted lesson + a failed job that originally planned all three."""
    config = _generate_first(scheme, allocations[0])
    with TestClient(_app(db, user)) as client:
        first = client.post(
            f"/api/generation/{scheme.id}/generate",
            json=config.model_dump(mode="json"))
    assert first.status_code == 200, first.text
    job_id = first.json()["job_id"]

    job = db.query(GenerationJobDB).filter(GenerationJobDB.id == job_id).first()
    snapshot = dict(job.config_snapshot or {})
    snapshot["planned_occurrence_ids"] = [
        a.source_occurrence_id for a in allocations]
    job.config_snapshot = snapshot
    job.status = "failed"
    job.error_message = "server restart interrupted the batch"
    job.completed_at = datetime.utcnow()
    db.commit()
    return job, first.json()


def test_normal_generate_persists_the_planned_occurrence_set(db):
    user = make_user(db)
    scheme = _scheme(db, user.id)
    allocations = _allocations(scheme, _config(scheme.id))

    with TestClient(_app(db, user)) as client:
        resp = client.post(
            f"/api/generation/{scheme.id}/generate",
            json=_config(scheme.id).model_dump(mode="json"))

    assert resp.status_code == 200, resp.text
    job = db.query(GenerationJobDB).filter(
        GenerationJobDB.id == resp.json()["job_id"]).first()
    planned = (job.config_snapshot or {}).get("planned_occurrence_ids")
    assert set(planned or []) == {
        a.source_occurrence_id for a in allocations}


def test_resume_runs_only_pending_occurrences_on_the_same_job(db):
    user = make_user(db)
    scheme = _scheme(db, user.id)
    allocations = _allocations(scheme, _config(scheme.id))
    job, first = _partial_job(db, user, scheme, allocations)
    before = _state(db, user, scheme)
    existing_id = before["lessons"][0].id

    with TestClient(_app(db, user)) as client:
        resp = client.post(
            f"/api/generation/{scheme.id}/generate/resume",
            json={"job_id": job.id})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["job_id"] == job.id, "resume must reuse the original job"
    assert set(body["generated_occurrence_ids"]) == {
        allocations[1].source_occurrence_id,
        allocations[2].source_occurrence_id,
    }
    assert body["resumable_occurrence_ids"] == []
    assert body["resumed"] is True

    after = _state(db, user, scheme)
    assert len(after["lessons"]) == 3
    assert {lp.id for lp in after["lessons"]} >= {existing_id}
    assert len(after["units"]) == 3
    assert after["units_used"] == 3
    assert after["job"].status == "completed"


def test_resume_is_idempotent_and_never_double_charges(db):
    user = make_user(db)
    scheme = _scheme(db, user.id)
    allocations = _allocations(scheme, _config(scheme.id))
    job, _ = _partial_job(db, user, scheme, allocations)

    with TestClient(_app(db, user)) as client:
        first = client.post(
            f"/api/generation/{scheme.id}/generate/resume",
            json={"job_id": job.id})
        second = client.post(
            f"/api/generation/{scheme.id}/generate/resume",
            json={"job_id": job.id})

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json()["generated_occurrence_ids"] == []
    assert second.json()["resumable_occurrence_ids"] == []

    state = _state(db, user, scheme)
    assert len(state["lessons"]) == 3
    assert len(state["units"]) == 3
    assert state["units_used"] == 3


def test_resume_late_failure_keeps_existing_lessons_and_rolls_back_new_ones(db):
    user = make_user(db)
    scheme = _scheme(db, user.id)
    allocations = _allocations(scheme, _config(scheme.id))
    job, _ = _partial_job(db, user, scheme, allocations)
    before = _state(db, user, scheme)

    from src import service as service_module
    with patch.object(
        service_module.data_service,
        "delete_lesson_plans_by_ids",
        side_effect=RuntimeError("simulated late resume failure"),
    ):
        with TestClient(_app(db, user)) as client:
            resp = client.post(
                f"/api/generation/{scheme.id}/generate/resume",
                json={"job_id": job.id})

    assert resp.status_code == 500, resp.text
    after = _state(db, user, scheme)
    assert len(after["lessons"]) == 1
    assert after["lessons"][0].id == before["lessons"][0].id
    assert len(after["units"]) == 1
    assert after["units_used"] == 1
    assert after["job"].status == "failed"


def test_resume_without_quota_capacity_does_no_work(db):
    user = make_user(db)
    scheme = _scheme(db, user.id)
    allocations = _allocations(scheme, _config(scheme.id))
    job, _ = _partial_job(db, user, scheme, allocations)

    # Saturate the Free Tier period after the first lesson. The period row is
    # authoritative for the guard; the unit ledger is kept internally
    # consistent so this is a valid "allowance exhausted" state.
    period_key = current_period_key()
    period = db.query(UsagePeriodDB).filter(
        UsagePeriodDB.user_id == user.id,
        UsagePeriodDB.period_key == period_key).first()
    assert period is not None
    period.units_used = 5
    db.query(UsageUnitDB).filter(
        UsageUnitDB.user_id == user.id,
        UsageUnitDB.period_key == period_key,
    ).delete(synchronize_session=False)
    for n in range(5):
        db.add(UsageUnitDB(
            id=generate_id(), user_id=user.id,
            period_type="calendar_month", period_key=period_key,
            unit_kind="lesson_plan",
            unit_key=f"{scheme.id}:filler-{n}",
            scheme_id=scheme.id, created_at=datetime.utcnow()))
    db.commit()

    with TestClient(_app(db, user)) as client:
        resp = client.post(
            f"/api/generation/{scheme.id}/generate/resume",
            json={"job_id": job.id})

    assert resp.status_code in (403, 409), resp.text
    state = _state(db, user, scheme)
    assert len(state["lessons"]) == 1
    assert len(state["units"]) == 5
    assert state["units_used"] == 5
    assert state["job"].status == "failed"


def test_latest_status_exposes_resumable_occurrences(db):
    user = make_user(db)
    scheme = _scheme(db, user.id)
    allocations = _allocations(scheme, _config(scheme.id))
    job, _ = _partial_job(db, user, scheme, allocations)

    with TestClient(_app(db, user)) as client:
        resp = client.get(f"/api/generation/scheme/{scheme.id}/status")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "failed"
    assert body["can_resume"] is True
    assert set(body["resumable_occurrence_ids"]) == {
        allocations[1].source_occurrence_id,
        allocations[2].source_occurrence_id,
    }

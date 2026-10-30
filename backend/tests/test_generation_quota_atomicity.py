"""Quota integrity when generation fails after lessons were persisted.

The audit reproduced a late failure (replacement delete/rehome) AFTER the
accepted lessons had already been committed. The job was marked failed and the
whole reservation was released, so the database held lesson rows that had been
charged ZERO quota units — a way to obtain lesson plans without consuming the
Free Tier allowance.

These tests assert DATABASE state (lesson rows, per-unit ledger rows and the
aggregate counter), not just the HTTP status. Run them against the production
driver with ``TEACHFLOW_TEST_DATABASE_URL=postgresql+psycopg://...``.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.database import (  # noqa: E402
    GenerationJobDB, LessonPlanDB, SchemeDB, UsagePeriodDB, UsageUnitDB,
    WeekDB, generate_id,
)
from src.usage_quota import current_period_key  # noqa: E402
from tests.conftest import make_user  # noqa: E402


@pytest.fixture(autouse=True)
def _wide_free_allowance(monkeypatch):
    """These scenarios drive 3 units per run.

    They exercise multi-unit atomicity, not the size of the Adesua allowance,
    so give the free tier room for a full run (the production limit is 2).
    """
    from src import entitlements

    monkeypatch.setattr(entitlements, "FREE_TIER_LESSON_PLANS_PER_MONTH", 5)


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


def _config(scheme_id, ai_mode="OFF"):
    from src.models import TermConfig

    return TermConfig(
        scheme_of_work_id=scheme_id,
        term_start_date=date(2026, 9, 7), term_end_date=date(2026, 12, 18),
        lessons_per_week=3, lesson_duration_minutes=60, class_size=30,
        teaching_days=[0, 2, 4], holidays=[], ai_mode=ai_mode,
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


def _db_state(db, user, scheme):
    db.expire_all()
    lessons = (
        db.query(LessonPlanDB)
        .filter(LessonPlanDB.owner_id == user.id,
                LessonPlanDB.scheme_id == scheme.id)
        .count()
    )
    period_key = current_period_key()
    units = (
        db.query(UsageUnitDB)
        .filter(UsageUnitDB.user_id == user.id,
                UsageUnitDB.period_key == period_key)
        .count()
    )
    period = (
        db.query(UsagePeriodDB)
        .filter(UsagePeriodDB.user_id == user.id,
                UsagePeriodDB.period_key == period_key)
        .first()
    )
    job = (
        db.query(GenerationJobDB)
        .filter(GenerationJobDB.owner_id == user.id,
                GenerationJobDB.scheme_id == scheme.id)
        .order_by(GenerationJobDB.created_at.desc())
        .first()
    )
    return {
        "lessons": lessons,
        "units": units,
        "units_used": int(period.units_used or 0) if period else 0,
        "job_status": job.status if job else None,
        "job_id": job.id if job else None,
        "finalization_warning": (
            (job.config_snapshot or {}).get("finalization_warning")
            if job else None
        ),
    }


def _generate(db, user, scheme, config=None):
    config = config or _config(scheme.id)
    with TestClient(_app(db, user)) as client:
        return client.post(
            f"/api/generation/{scheme.id}/generate",
            json=config.model_dump(mode="json"),
        )


def test_failure_while_replacing_old_lessons_rolls_back_new_lesson_and_quota(db):
    """Failure in the replacement delete: either both persist or neither does."""
    from src import service as service_module

    user = make_user(db)
    scheme = _scheme(db, user.id)

    with patch.object(
        service_module.data_service,
        "delete_lesson_plans_by_ids",
        side_effect=RuntimeError("simulated late persistence failure"),
    ):
        resp = _generate(db, user, scheme)

    assert resp.status_code == 500, resp.text
    state = _db_state(db, user, scheme)
    assert state["lessons"] == 0, (
        "a failed run must not leave persisted lessons: "
        f"{state['lessons']} lesson row(s) survived")
    assert state["units"] == 0
    assert state["units_used"] == 0, (
        "quota ledger must match persisted lessons (no free lesson rows)")
    assert state["job_status"] == "failed"


def test_failure_while_rehoming_surviving_lessons_rolls_back_everything(db):
    """Failure in the rehome step has the same all-or-nothing contract."""
    from src import service as service_module

    user = make_user(db)
    scheme = _scheme(db, user.id)

    with patch.object(
        service_module.data_service,
        "rehome_lesson_plans_for_scheme",
        side_effect=RuntimeError("simulated late persistence failure"),
    ):
        resp = _generate(db, user, scheme)

    assert resp.status_code == 500, resp.text
    state = _db_state(db, user, scheme)
    assert state["lessons"] == 0
    assert state["units"] == 0
    assert state["units_used"] == 0
    assert state["job_status"] == "failed"


def test_successful_run_persists_lessons_and_charges_matching_units(db):
    """Control: a successful run leaves unit count == accepted-code count."""
    user = make_user(db)
    scheme = _scheme(db, user.id)

    resp = _generate(db, user, scheme)

    assert resp.status_code == 200, resp.text
    state = _db_state(db, user, scheme)
    assert state["lessons"] > 0
    assert state["units"] == 3, (
        "one unit per (scheme, indicator code): 3 codes in this scheme")
    assert state["units_used"] == state["units"]
    assert state["job_status"] == "completed"


# ── Post-commit failures: durable work is reported truthfully ───────────────
# Once lessons and units have committed, a later finalization error must not
# turn the request into a 500. The response is a recovered success built from
# durable state, and the warning is persisted on the job for the status page.


def test_post_commit_quota_read_failure_returns_recovered_success(db):
    from src import entitlements as entitlements_module

    user = make_user(db)
    scheme = _scheme(db, user.id)
    real_status = entitlements_module.lesson_quota_status
    calls = {"n": 0}

    def flaky_status(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise RuntimeError("simulated post-commit quota read failure")
        return real_status(*args, **kwargs)

    with patch.object(entitlements_module, "lesson_quota_status",
                      side_effect=flaky_status):
        resp = _generate(db, user, scheme)

    assert resp.status_code == 200, (
        "a committed run must not be reported as a 500: " + resp.text)
    body = resp.json()
    assert body["status"] == "completed"
    assert body["recovered"] is True
    assert body["finalization"]["state"] == "completed_with_warning"
    assert body["warning"]

    state = _db_state(db, user, scheme)
    assert state["lessons"] > 0, "durable lessons must remain"
    assert state["units"] == 3
    assert state["units_used"] == 3
    assert state["job_status"] == "completed"
    assert state["finalization_warning"], (
        "the finalization warning must be durable, not response-only")


def test_post_commit_activity_log_failure_returns_recovered_success(db):
    from src.routers import generation as gen_router

    user = make_user(db)
    scheme = _scheme(db, user.id)
    real_log = gen_router.log_event

    def flaky_log(event, *args, **kwargs):
        if event == "generation_completed":
            raise RuntimeError("simulated post-commit logging failure")
        return real_log(event, *args, **kwargs)

    with patch.object(gen_router, "log_event", side_effect=flaky_log):
        resp = _generate(db, user, scheme)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["recovered"] is True
    assert body["status"] == "completed"
    assert body["finalization"]["state"] == "completed_with_warning"
    state = _db_state(db, user, scheme)
    assert state["lessons"] > 0
    assert state["units"] == 3
    assert state["job_status"] == "completed"


def test_post_commit_ai_credit_failure_returns_recovered_success(db):
    from src.models import AIMode
    from src.routers import generation as gen_router

    user = make_user(db)
    scheme = _scheme(db, user.id)
    config = _config(scheme.id, ai_mode="BASIC")
    real_generate = gen_router.pipeline.generate_all

    def generate_then_mark_ai(scheme_model, effective_config, **kwargs):
        # Keep the pipeline deterministic while making the response think an
        # AI-assisted batch succeeded, so the post-commit credit path runs.
        original_mode = effective_config.ai_mode
        effective_config.ai_mode = AIMode.OFF
        try:
            job = real_generate(scheme_model, effective_config, **kwargs)
        finally:
            effective_config.ai_mode = original_mode
        job.ai_enrichment_succeeded = 1
        return job

    with patch.object(gen_router, "require_ai_entitlement",
                      side_effect=lambda *a, **k: None), \
         patch.object(gen_router, "consume_ai_generation",
                      side_effect=RuntimeError("simulated AI ledger failure")), \
         patch.object(gen_router.pipeline, "generate_all",
                      side_effect=generate_then_mark_ai):
        resp = _generate(db, user, scheme, config)

    assert resp.status_code == 200, (
        "a committed AI run whose credit ledger failed must not return 500: "
        + resp.text)
    body = resp.json()
    assert body["status"] == "completed"
    assert body["recovered"] is True
    assert body["finalization"]["state"] == "completed_with_warning"
    assert body["ai_credits_remaining"] is None
    assert "AI" in body["warning"] or "ai" in body["warning"].lower()

    state = _db_state(db, user, scheme)
    assert state["lessons"] > 0
    assert state["units"] == 3
    assert state["units_used"] == 3
    assert state["job_status"] == "completed"


def test_status_endpoint_surfaces_the_durable_finalization_warning(db):
    from src import entitlements as entitlements_module

    user = make_user(db)
    scheme = _scheme(db, user.id)
    real_status = entitlements_module.lesson_quota_status
    calls = {"n": 0}

    def flaky_status(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise RuntimeError("simulated post-commit quota read failure")
        return real_status(*args, **kwargs)

    with patch.object(entitlements_module, "lesson_quota_status",
                      side_effect=flaky_status):
        resp = _generate(db, user, scheme)
    assert resp.status_code == 200, resp.text

    job_id = resp.json()["job_id"]
    with TestClient(_app(db, user)) as client:
        status = client.get(f"/api/generation/{job_id}/status")
    assert status.status_code == 200, status.text
    payload = status.json()
    assert payload["status"] == "completed"
    assert payload["finalization_warning"]


def test_retry_after_post_commit_failure_is_idempotent(db):
    """The client retries after a lost response: no duplicates, no double charge."""
    from src import entitlements as entitlements_module

    user = make_user(db)
    scheme = _scheme(db, user.id)
    real_status = entitlements_module.lesson_quota_status
    calls = {"n": 0}

    def flaky_status(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise RuntimeError("simulated post-commit quota read failure")
        return real_status(*args, **kwargs)

    with patch.object(entitlements_module, "lesson_quota_status",
                      side_effect=flaky_status):
        first = _generate(db, user, scheme)
    assert first.status_code == 200, first.text
    before = _db_state(db, user, scheme)
    assert before["lessons"] > 0

    retry = _generate(db, user, scheme)
    assert retry.status_code == 200, retry.text
    after = _db_state(db, user, scheme)

    assert after["lessons"] == before["lessons"], (
        "a retry must replace in place, never duplicate the lesson set")
    assert after["units"] == before["units"] == 3
    assert after["units_used"] == 3, "the same scheme codes were charged once"
    assert after["job_status"] == "completed"


def test_pre_commit_failure_then_retry_succeeds_cleanly(db):
    """The other case: nothing committed, so the retry must do the real work."""
    from src import service as service_module

    user = make_user(db)
    scheme = _scheme(db, user.id)

    with patch.object(
        service_module.data_service,
        "delete_lesson_plans_by_ids",
        side_effect=RuntimeError("simulated pre-commit failure"),
    ):
        failed = _generate(db, user, scheme)

    assert failed.status_code == 500, failed.text
    failed_state = _db_state(db, user, scheme)
    assert failed_state["lessons"] == 0
    assert failed_state["units"] == 0
    assert failed_state["units_used"] == 0
    assert failed_state["job_status"] == "failed"

    retry = _generate(db, user, scheme)
    assert retry.status_code == 200, retry.text
    retried_state = _db_state(db, user, scheme)
    assert retried_state["lessons"] > 0
    assert retried_state["units"] == 3
    assert retried_state["units_used"] == 3
    assert retried_state["job_status"] == "completed"

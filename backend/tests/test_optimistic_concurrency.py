"""Optimistic-concurrency gates for lesson and weekly-plan saves.

A client that read revision R must not be able to overwrite revision R+1.
Lesson saves use the DB ``updated_at`` token; weekly plans use the stored
``updated_date`` revision. Both reject a stale If-Match with 409.
"""
from __future__ import annotations

import json
from datetime import date, datetime

import pytest
from fastapi import HTTPException

from src.database import GenerationJobDB, LessonPlanDB, SchemeDB, generate_id
from src.routers import generation, weekly_plans
from src.service import DataService
from tests.conftest import make_user


def _lesson_row(db):
    user = make_user(db, email=f"race-{generate_id()[:8]}@test.local")
    scheme = SchemeDB(
        id=generate_id(), owner_id=user.id, filename="Race Scheme.pdf",
        subject="Science", class_level="Basic 8", term="First Term",
    )
    db.add(scheme)
    db.flush()
    job = GenerationJobDB(
        id=generate_id(), owner_id=user.id, scheme_id=scheme.id,
        status="completed", completed_lessons=1,
    )
    db.add(job)
    db.flush()
    lp = LessonPlanDB(
        id=generate_id(), job_id=job.id, owner_id=user.id,
        scheme_id=scheme.id, week_number=1, lesson_sequence=1,
        lesson_number=1, lesson_date=date(2026, 9, 11),
        class_level="Basic 8", subject="Science",
        lesson_topic="Original topic",
    )
    db.add(lp)
    db.commit()
    db.refresh(lp)
    return user, lp


def test_lesson_save_with_matching_version_succeeds_and_advances(db):
    user, lp = _lesson_row(db)
    version = lp.updated_at.isoformat()

    updated = DataService().update_lesson_plan(
        db, lp.id, user.id, {"lesson_topic": "Edited once"},
        expected_version=version,
    )

    assert updated is not None
    assert updated.lesson_topic == "Edited once"
    assert updated.updated_at.isoformat() != version


def test_stale_lesson_version_is_rejected_without_mutation(db):
    user, lp = _lesson_row(db)
    stale = lp.updated_at.isoformat()

    DataService().update_lesson_plan(
        db, lp.id, user.id, {"lesson_topic": "First writer"},
    )
    db.expire_all()

    with pytest.raises(Exception) as exc:
        DataService().update_lesson_plan(
            db, lp.id, user.id, {"lesson_topic": "Second writer"},
            expected_version=stale,
        )
    assert exc.type.__name__ == "StaleLessonVersionError"

    db.expire_all()
    stored = db.query(LessonPlanDB).filter(LessonPlanDB.id == lp.id).one()
    assert stored.lesson_topic == "First writer"


@pytest.mark.asyncio
async def test_lesson_route_returns_409_for_stale_if_match(db, monkeypatch):
    user, lp = _lesson_row(db)
    stale = lp.updated_at.isoformat()
    DataService().update_lesson_plan(
        db, lp.id, user.id, {"lesson_topic": "First writer"},
    )

    with pytest.raises(HTTPException) as exc:
        await generation.update_lesson_plan(
            lp.id, {"lesson_topic": "Second writer"}, user, db, if_match=stale,
        )
    assert exc.value.status_code == 409
    assert "changed since" in str(exc.value.detail)


def _write_weekly_store(tmp_path, updated_date="2026-01-01T10:00:00"):
    plan = {
        "id": "wp-race",
        "owner_id": "owner-1",
        "class_level": "Basic 1",
        "week_number": 1,
        "term": "First Term",
        "academic_year": "2026/2027",
        "template_id": "wapef_basic13",
        "school_name": "School",
        "teacher_name": "Teacher",
        "subjects": [],
        "created_date": "2026-01-01T09:00:00",
        "updated_date": updated_date,
    }
    store = {"plans": [{
        "id": "wp-race", "owner_id": "owner-1",
        "class_level": "Basic 1", "week_number": 1, "term": "First Term",
        "academic_year": "2026/2027", "template_id": "wapef_basic13",
        "school_name": "School", "teacher_name": "Teacher",
        "created_date": "2026-01-01T09:00:00",
        "updated_date": updated_date,
        "plan": plan,
    }]}
    path = tmp_path / "weekly_plans.json"
    path.write_text(json.dumps(store), encoding="utf-8")
    return path


class _User:
    id = "owner-1"


@pytest.mark.asyncio
async def test_weekly_plan_stale_version_is_rejected(tmp_path, monkeypatch):
    path = _write_weekly_store(tmp_path)
    monkeypatch.setattr(weekly_plans, "_PLANS_FILE", path)
    user = _User()

    first = await weekly_plans.update_weekly_plan(
        "wp-race", {"subjects": []}, user, if_match="2026-01-01T10:00:00",
    )
    assert first["version"] != "2026-01-01T10:00:00"

    with pytest.raises(HTTPException) as exc:
        await weekly_plans.update_weekly_plan(
            "wp-race", {"subjects": []}, user, if_match="2026-01-01T10:00:00",
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_weekly_plan_save_without_header_remains_backward_compatible(tmp_path, monkeypatch):
    path = _write_weekly_store(tmp_path)
    monkeypatch.setattr(weekly_plans, "_PLANS_FILE", path)
    result = await weekly_plans.update_weekly_plan(
        "wp-race", {"subjects": []}, _User(), if_match=None,
    )
    assert result["plan"]["id"] == "wp-race"
    assert result["version"]

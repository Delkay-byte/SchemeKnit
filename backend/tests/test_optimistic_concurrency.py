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


def _weekly_plan():
    from src.models import WeeklyClassPlan, SubjectPlan, SubjectMetadata, DayPlan
    return WeeklyClassPlan(
        id="wp-race", owner_id="owner-1", class_level="Basic 1", week_number=1,
        term="First Term", academic_year="2026/2027",
        school_name="School", teacher_name="Teacher", template_id="wapef_basic13",
        subjects=[SubjectPlan(
            subject="English Language", teaching_days=["MONDAY"],
            teaching_day_groups=[["MONDAY"]],
            metadata=SubjectMetadata(subject="English Language", class_level="Basic 1"),
            day_plans=[DayPlan(days=["MONDAY"], day_label="MONDAY",
                               starter="Original", reflection="Original")],
        )],
    )


def test_weekly_plan_create_get_and_ownership(db):
    from src.weekly_plan_store import (
        WeeklyPlanNotFound, create_row, get_row, version_token,
    )
    user = make_user(db, email="weekly-owner@test.local")
    row = create_row(db, owner_id=user.id, plan=_weekly_plan())
    assert row.revision == 1
    assert version_token(row) == "1"
    assert get_row(db, "wp-race", user.id).id == "wp-race"
    with pytest.raises(WeeklyPlanNotFound):
        get_row(db, "wp-race", "someone-else")


def test_weekly_plan_update_with_correct_revision(db):
    from src.weekly_plan_store import create_row, get_row, plan_from_row, update_row
    user = make_user(db, email="weekly-update@test.local")
    create_row(db, owner_id=user.id, plan=_weekly_plan())
    plan = plan_from_row(get_row(db, "wp-race", user.id))
    plan.subjects[0].day_plans[0].starter = "First writer"

    updated = update_row(
        db, plan_id="wp-race", owner_id=user.id,
        content=plan.model_dump(mode="json"), expected_version="1",
    )
    assert updated.revision == 2
    assert plan_from_row(updated).subjects[0].day_plans[0].starter == "First writer"


def test_weekly_plan_stale_revision_is_rejected_without_write(db):
    from src.weekly_plan_store import (
        StaleWeeklyPlanRevision, create_row, get_row, plan_from_row, update_row,
    )
    user = make_user(db, email="weekly-stale@test.local")
    create_row(db, owner_id=user.id, plan=_weekly_plan())
    plan = plan_from_row(get_row(db, "wp-race", user.id))
    plan.subjects[0].day_plans[0].starter = "First writer"
    update_row(db, plan_id="wp-race", owner_id=user.id,
               content=plan.model_dump(mode="json"), expected_version="1")

    second = _weekly_plan()
    second.subjects[0].day_plans[0].starter = "Second writer"
    with pytest.raises(StaleWeeklyPlanRevision):
        update_row(db, plan_id="wp-race", owner_id=user.id,
                   content=second.model_dump(mode="json"), expected_version="1")

    db.expire_all()
    stored = get_row(db, "wp-race", user.id)
    assert plan_from_row(stored).subjects[0].day_plans[0].starter == "First writer"
    assert stored.revision == 2


@pytest.mark.asyncio
async def test_weekly_route_returns_409_for_stale_if_match(db):
    from src.weekly_plan_store import create_row
    user = make_user(db, email="weekly-route@test.local")
    create_row(db, owner_id=user.id, plan=_weekly_plan())

    with pytest.raises(HTTPException) as exc:
        await weekly_plans.update_weekly_plan(
            "wp-race",
            {"subjects": [{"index": 0, "day_plans": [{"index": 0, "starter": "New"}]}]},
            user, db, if_match="9",
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_weekly_route_persists_and_returns_new_revision(db):
    from src.weekly_plan_store import create_row
    user = make_user(db, email="weekly-route-ok@test.local")
    create_row(db, owner_id=user.id, plan=_weekly_plan())

    result = await weekly_plans.update_weekly_plan(
        "wp-race",
        {"subjects": [{"index": 0, "day_plans": [{"index": 0, "starter": "New"}]}]},
        user, db, if_match="1",
    )
    assert result["version"] == "2"
    assert result["plan"]["subjects"][0]["day_plans"][0]["starter"] == "New"


@pytest.mark.asyncio
async def test_weekly_route_db_failure_is_controlled(db, monkeypatch):
    from sqlalchemy.exc import OperationalError
    from src.weekly_plan_store import create_row
    user = make_user(db, email="weekly-db-down@test.local")
    create_row(db, owner_id=user.id, plan=_weekly_plan())

    def unavailable(*args, **kwargs):
        raise OperationalError("select", {}, Exception("connection lost"))

    monkeypatch.setattr(weekly_plans, "get_row", unavailable)
    with pytest.raises(HTTPException) as exc:
        await weekly_plans.get_weekly_plan("wp-race", user, db)
    assert exc.value.status_code == 503
    assert "temporarily unavailable" in str(exc.value.detail)


def test_sqlite_concurrent_writers_use_database_revision(tmp_path):
    """SQLite keeps the same functional guarantee: one CAS winner."""
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from src.database import Base, User
    from src.weekly_plan_store import StaleWeeklyPlanRevision, create_row, update_row

    engine = create_engine(
        f"sqlite:///{tmp_path / 'weekly.db'}",
        connect_args={"timeout": 10},
    )
    Base.metadata.create_all(engine)
    owner = "sqlite-owner"
    with Session(engine) as db:
        db.add(User(id=owner, email="sqlite-owner@test.local", full_name="Owner",
                    hashed_password="x", role="teacher", is_admin=False, is_active=True))
        db.commit()
        create_row(db, owner_id=owner, plan=_weekly_plan())

    def writer(starter):
        with Session(engine) as db:
            doc = _weekly_plan().model_dump(mode="json")
            doc["subjects"][0]["day_plans"][0]["starter"] = starter
            try:
                row = update_row(db, plan_id="wp-race", owner_id=owner,
                                 content=doc, expected_version="1")
                return f"ok:{row.revision}"
            except StaleWeeklyPlanRevision:
                return "stale"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(writer, ["SQLite A", "SQLite B"]))
    assert sorted(outcomes) == ["ok:2", "stale"]
    engine.dispose()

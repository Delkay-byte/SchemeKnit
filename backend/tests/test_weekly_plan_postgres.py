"""Real PostgreSQL concurrency acceptance for weekly plans.

Skipped unless a disposable PostgreSQL URL is provided. CI's `postgres` job
runs this alongside the migration harness. The database is a scratch database;
fixtures are created and removed by the test.
"""
from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.database import Base, User
from src.models import DayPlan, SubjectMetadata, SubjectPlan, WeeklyClassPlan
from src.weekly_plan_store import (
    StaleWeeklyPlanRevision, create_row, get_row, plan_from_row, update_row,
)


def _url():
    for key in ("POSTGRES_MIGRATION_TEST_URL", "TEACHFLOW_TEST_DATABASE_URL"):
        url = os.environ.get(key, "")
        if url.startswith("postgres"):
            if url.startswith("postgresql://"):
                url = "postgresql+psycopg://" + url[len("postgresql://"):]
            return url
    return None


pytestmark = pytest.mark.skipif(
    _url() is None,
    reason="Set POSTGRES_MIGRATION_TEST_URL to a scratch PostgreSQL database",
)


@pytest.fixture()
def pg_engine():
    engine = create_engine(_url())
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


def _plan(plan_id: str, owner_id: str, starter: str = "Original") -> WeeklyClassPlan:
    return WeeklyClassPlan(
        id=plan_id, owner_id=owner_id, class_level="Basic 1", week_number=1,
        term="First Term", academic_year="2026/2027",
        school_name="School", teacher_name="Teacher", template_id="wapef_basic13",
        subjects=[SubjectPlan(
            subject="English Language", teaching_days=["MONDAY"],
            teaching_day_groups=[["MONDAY"]],
            metadata=SubjectMetadata(subject="English Language", class_level="Basic 1"),
            day_plans=[DayPlan(days=["MONDAY"], day_label="MONDAY",
                               starter=starter, reflection="Original")],
        )],
    )


def _user(engine):
    user_id = str(uuid.uuid4())
    with Session(engine) as db:
        db.add(User(
            id=user_id, email=f"pg-weekly-{user_id[:8]}@test.local",
            full_name="Postgres Weekly", hashed_password="x",
            role="teacher", is_admin=False, is_active=True,
        ))
        db.commit()
    return user_id


def test_two_connections_with_same_revision_only_one_wins(pg_engine):
    owner = _user(pg_engine)
    plan_id = f"wp-{uuid.uuid4()}"
    with Session(pg_engine) as db:
        create_row(db, owner_id=owner, plan=_plan(plan_id, owner))
        assert get_row(db, plan_id, owner).revision == 1

    def writer(starter: str) -> str:
        with Session(pg_engine) as db:
            document = _plan(plan_id, owner, starter).model_dump(mode="json")
            try:
                updated = update_row(
                    db, plan_id=plan_id, owner_id=owner,
                    content=document, expected_version="1",
                )
                return f"ok:{updated.revision}"
            except StaleWeeklyPlanRevision:
                return "stale"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(writer, ["Connection A", "Connection B"]))

    assert sorted(outcomes) == ["ok:2", "stale"]

    with Session(pg_engine) as db:
        stored = get_row(db, plan_id, owner)
        # The surviving document is one complete writer, never a mixture.
        assert stored.revision == 2
        assert plan_from_row(stored).subjects[0].day_plans[0].starter in {
            "Connection A", "Connection B",
        }


def test_stale_writer_cannot_overwrite_after_commit(pg_engine):
    owner = _user(pg_engine)
    plan_id = f"wp-{uuid.uuid4()}"
    with Session(pg_engine) as db:
        create_row(db, owner_id=owner, plan=_plan(plan_id, owner))

    with Session(pg_engine) as first:
        row = get_row(first, plan_id, owner)
        plan = plan_from_row(row)
        plan.subjects[0].day_plans[0].starter = "First"
        update_row(first, plan_id=plan_id, owner_id=owner,
                   content=plan.model_dump(mode="json"), expected_version="1")

    with Session(pg_engine) as second:
        stale = _plan(plan_id, owner, "Stale")
        with pytest.raises(StaleWeeklyPlanRevision):
            update_row(second, plan_id=plan_id, owner_id=owner,
                       content=stale.model_dump(mode="json"),
                       expected_version="1")

    with Session(pg_engine) as db:
        stored = get_row(db, plan_id, owner)
        assert stored.revision == 2
        assert plan_from_row(stored).subjects[0].day_plans[0].starter == "First"


def test_schema_starts_empty_and_is_owner_isolated(pg_engine):
    owner = _user(pg_engine)
    other = _user(pg_engine)
    with Session(pg_engine) as db:
        assert db.query(__import__(
            "src.database", fromlist=["WeeklyPlanDB"]).WeeklyPlanDB).count() == 0
        create_row(db, owner_id=owner, plan=_plan("wp-owned", owner))
        from src.weekly_plan_store import WeeklyPlanNotFound
        with pytest.raises(WeeklyPlanNotFound):
            get_row(db, "wp-owned", other)


def test_v051_migration_creates_table_from_baseline(pg_engine, monkeypatch):
    """Rehearse the additive migration when the table does not pre-exist."""
    import importlib
    from sqlalchemy import inspect

    from src.database import SessionLocal

    with pg_engine.begin() as conn:
        conn.execute(__import__("sqlalchemy").text(
            "DROP TABLE IF EXISTS weekly_class_plans CASCADE"))
    assert not inspect(pg_engine).has_table("weekly_class_plans")

    migration = importlib.import_module("src.migrations.v051_weekly_class_plans")
    monkeypatch.setattr(migration, "engine", pg_engine)
    db = Session(pg_engine)
    try:
        migration.up(db)
    finally:
        db.close()

    assert inspect(pg_engine).has_table("weekly_class_plans")
    with Session(pg_engine) as db:
        from src.database import WeeklyPlanDB
        assert db.query(WeeklyPlanDB).count() == 0

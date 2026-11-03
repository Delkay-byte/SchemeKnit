"""Legacy JSON importer: dry-run, validation and idempotency."""
import importlib.util
import json
from pathlib import Path

from src.database import WeeklyPlanDB
from src.models import DayPlan, SubjectMetadata, SubjectPlan, WeeklyClassPlan
from tests.conftest import make_user


def _load_importer():
    path = Path(__file__).resolve().parents[1] / "scripts" / "import_weekly_plans.py"
    spec = importlib.util.spec_from_file_location("weekly_importer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _record(owner_id, plan_id="legacy-plan"):
    plan = WeeklyClassPlan(
        id=plan_id, owner_id=owner_id, class_level="Basic 1", week_number=1,
        term="First Term", academic_year="2026/2027",
        subjects=[SubjectPlan(
            subject="English", metadata=SubjectMetadata(subject="English"),
            day_plans=[DayPlan(days=["MONDAY"])],
        )],
    )
    return {
        "id": plan_id, "owner_id": owner_id, "class_level": "Basic 1",
        "week_number": 1, "term": "First Term", "academic_year": "2026/2027",
        "template_id": "wapef_basic13", "school_name": None,
        "teacher_name": None, "created_date": "2026-01-01T00:00:00",
        "updated_date": "2026-01-01T00:00:00",
        "plan": plan.model_dump(mode="json"),
    }


def test_importer_dry_run_then_apply_is_idempotent(db, tmp_path, monkeypatch):
    importer = _load_importer()
    user = make_user(db, email="legacy-owner@test.local")
    path = tmp_path / "weekly_plans.json"
    path.write_text(json.dumps({"plans": [_record(user.id)]}), encoding="utf-8")
    monkeypatch.setattr(importer, "SessionLocal", lambda: db)

    assert importer.run(path, apply=False) == 0
    assert db.query(WeeklyPlanDB).count() == 0

    assert importer.run(path, apply=True) == 0
    db.expire_all()
    assert db.query(WeeklyPlanDB).count() == 1

    assert importer.run(path, apply=True) == 0
    db.expire_all()
    assert db.query(WeeklyPlanDB).count() == 1


def test_importer_reports_records_with_unknown_owner(db, tmp_path, monkeypatch):
    importer = _load_importer()
    path = tmp_path / "weekly_plans.json"
    path.write_text(
        json.dumps({"plans": [_record("missing-owner")]}), encoding="utf-8")
    monkeypatch.setattr(importer, "SessionLocal", lambda: db)

    assert importer.run(path, apply=False) == 1
    assert db.query(WeeklyPlanDB).count() == 0

"""v057 Zeli pedagogy: persistence, read-model parity and export fidelity.

The quality gate is worthless if worked examples, answered practice and
low-cost resource guidance vanish on reload or in the downloaded DOCX. These
tests follow one lesson from the additive migration, through the DB row and
the API read model, into both export renderers.
"""
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from docx import Document
from sqlalchemy import create_engine, inspect as sa_inspect, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import (  # noqa: E402
    Base, GenerationJobDB, LessonPlanDB, SchemeDB, generate_id,
)
from src.engines.docx_export import DOCXExportEngine  # noqa: E402
from src.engines.export_model import _assessment_appendix  # noqa: E402
from src.models import LessonPlan, Subject  # noqa: E402
from src.routers.generation import _serialize_lesson  # noqa: E402
from tests.conftest import make_user  # noqa: E402

NEW_COLUMNS = ("worked_example", "practice_questions", "resource_guidance")

WORKED = {
    "problem": "Represent 247 with bundles of ten and loose sticks.",
    "steps": ["Count 24 bundles of ten.", "Add 7 loose sticks.", "Write 247."],
    "answer": "247",
    "reasoning": "24 tens are 240, plus 7 ones gives 247.",
}
QUESTIONS = [{
    "question": "Represent 318 with bundles of ten and loose sticks.",
    "expected_answer": "318",
    "reasoning": "31 tens and 8 ones.",
}]
GUIDANCE = {
    "preparation": "Collect 40 sticks and tie them into bundles of ten.",
    "use": "Learners regroup sticks in pairs before writing the numeral.",
    "no_cost_alternative": "Use bottle tops in place of sticks.",
}


class TestV057Migration:
    @pytest.fixture
    def legacy_db(self, tmp_path, monkeypatch):
        engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE lesson_plans (id VARCHAR PRIMARY KEY)"))
        Session = sessionmaker(bind=engine)
        db = Session()
        from src.migrations import v057_zeli_pedagogy_fields as migration
        monkeypatch.setattr(migration, "engine", engine)
        yield db, engine, migration
        db.close()
        engine.dispose()

    def test_adds_three_json_columns_to_legacy_table(self, legacy_db):
        db, engine, migration = legacy_db
        migration.up(db)
        cols = {c["name"] for c in sa_inspect(engine).get_columns("lesson_plans")}
        assert set(NEW_COLUMNS) <= cols

    def test_idempotent_and_down_is_non_destructive(self, legacy_db):
        db, engine, migration = legacy_db
        migration.up(db)
        migration.up(db)
        migration.down(db)
        cols = {c["name"] for c in sa_inspect(engine).get_columns("lesson_plans")}
        assert set(NEW_COLUMNS) <= cols

    def test_orm_declares_every_new_column(self):
        cols = set(LessonPlanDB.__table__.columns.keys())
        assert set(NEW_COLUMNS) <= cols

    def test_runner_discovers_v057_after_v056(self):
        migration_dir = Path(__file__).parent.parent / "src" / "migrations"
        versions = sorted(p.stem for p in migration_dir.glob("v*.py"))
        assert "v057_zeli_pedagogy_fields" in versions
        assert versions.index("v057_zeli_pedagogy_fields") > versions.index(
            "v051_weekly_class_plans")


def _stored_lesson(db):
    user = make_user(db)
    scheme = SchemeDB(
        id=generate_id(), owner_id=user.id, filename="B4 Maths.docx",
        subject="Mathematics", class_level="Basic 4", term="First Term",
    )
    db.add(scheme)
    job = GenerationJobDB(
        id=generate_id(), owner_id=user.id, scheme_id=scheme.id,
        status="completed", completed_lessons=1,
    )
    db.add(job)
    db.flush()
    lp = LessonPlanDB(
        id=generate_id(), job_id=job.id, owner_id=user.id, scheme_id=scheme.id,
        week_number=1, lesson_sequence=1, lesson_number=1,
        lesson_date=date(2026, 9, 11) + timedelta(days=7),
        class_level="Basic 4", subject="Mathematics", class_size=28,
        duration_minutes=60, school_name="Kpogede Community School",
        teacher_name="A. Teacher", strand="Numbers",
        sub_strand="Counting, Representation & Cardinality",
        content_standard="B4.1.1.1", indicators=["B4.1.1.1.1 Represent 247"],
        lesson_topic="Representing two-digit numbers",
        introduction="Review counting.", assessment="Check the regrouping.",
        conclusion="Summarise.", worked_example=WORKED,
        practice_questions=QUESTIONS, resource_guidance=GUIDANCE,
    )
    db.add(lp)
    db.commit()
    db.expunge_all()
    return db.query(LessonPlanDB).one(), db.query(SchemeDB).one()


def test_lesson_row_round_trips_v057_fields(db):
    lp, _ = _stored_lesson(db)
    assert lp.worked_example == WORKED
    assert lp.practice_questions == QUESTIONS
    assert lp.resource_guidance == GUIDANCE


def test_api_read_model_matches_stored_pedagogy(db):
    lp, scheme = _stored_lesson(db)
    body = _serialize_lesson(lp, scheme)
    assert body["worked_example"] == WORKED
    assert body["practice_questions"] == QUESTIONS
    assert body["resource_guidance"] == GUIDANCE


def test_export_model_appendix_carries_pedagogy():
    lesson = LessonPlan(
        scheme_of_work_id="s", term_config_id="j", week_number=1,
        lesson_sequence=1, lesson_date=date(2026, 9, 18), lesson_number=1,
        school_name="Kpogede Community School", teacher_name="A. Teacher",
        subject=Subject.MATHEMATICS, class_level="Basic 4", class_size=28,
        duration_minutes=60, strand="Numbers",
        sub_strand="Counting, Representation & Cardinality",
        content_standard="B4.1.1.1", indicators=["B4.1.1.1.1 Represent 247"],
        lesson_topic="Representing two-digit numbers",
        worked_example=WORKED, practice_questions=QUESTIONS,
        resource_guidance=GUIDANCE,
    )
    blocks = _assessment_appendix(lesson)
    text = " ".join(str(block.get("text") or "") for block in blocks)
    assert "Worked Example" in text
    assert WORKED["problem"] in text
    assert WORKED["reasoning"] in text
    assert QUESTIONS[0]["question"] in text
    assert QUESTIONS[0]["expected_answer"] in text
    assert "Low-Cost Resource Guidance" in text
    assert GUIDANCE["no_cost_alternative"] in text


def test_exported_docx_prints_pedagogy(tmp_path):
    lesson = LessonPlan(
        scheme_of_work_id="s", term_config_id="j", week_number=1,
        lesson_sequence=1, lesson_date=date(2026, 9, 18), lesson_number=1,
        school_name="Kpogede Community School", teacher_name="A. Teacher",
        subject=Subject.MATHEMATICS, class_level="Basic 4", class_size=28,
        duration_minutes=60, strand="Numbers",
        sub_strand="Counting, Representation & Cardinality",
        content_standard="B4.1.1.1", indicators=["B4.1.1.1.1 Represent 247"],
        lesson_topic="Representing two-digit numbers",
        worked_example=WORKED, practice_questions=QUESTIONS,
        resource_guidance=GUIDANCE,
    )
    out = tmp_path / "zeli.docx"
    DOCXExportEngine().export_official_ges([lesson], out)
    doc = Document(str(out))
    text = "\n".join(
        [p.text for p in doc.paragraphs]
        + [c.text for table in doc.tables for row in table.rows for c in row.cells]
    )
    assert "Worked Example" in text
    assert WORKED["problem"] in text
    assert QUESTIONS[0]["question"] in text
    assert QUESTIONS[0]["expected_answer"] in text
    assert "Low-Cost Resource Guidance" in text
    assert GUIDANCE["preparation"] in text

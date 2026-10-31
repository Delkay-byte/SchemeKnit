"""Mass-assignment regression tests for the lesson save boundary.

The ordinary lesson-update endpoint edits teacher-owned content only. It must
never write provenance, tenant, ownership, curriculum-identity or structural
fields, and a rejected payload must leave the row untouched.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException
from docx import Document

from tests.conftest import make_user
from src.database import (
    GenerationJobDB, LessonPlanDB, SchemeDB, generate_id,
)
from src.routers import generation
from src.service import (
    DataService, UnsupportedLessonFieldError, normalize_lesson_updates,
)


def _lesson(db, owner, *, school_id=None):
    scheme = SchemeDB(
        id=generate_id(), owner_id=owner.id, school_id=school_id,
        filename="Basic 9 Science.docx", subject="Science",
        class_level="Basic 9", term="First Term",
    )
    db.add(scheme)
    db.flush()
    job = GenerationJobDB(
        id=generate_id(), owner_id=owner.id, scheme_id=scheme.id,
        status="completed", completed_lessons=1,
    )
    db.add(job)
    db.flush()
    lp = LessonPlanDB(
        id=generate_id(), job_id=job.id, owner_id=owner.id,
        scheme_id=scheme.id, school_id=school_id,
        week_number=1, lesson_sequence=1, lesson_number=1,
        lesson_date=date(2026, 9, 11), class_level="Basic 9",
        subject="Science", school_name="Original School",
        teacher_name="Original Teacher", strand="Diversity of Matter",
        sub_strand="Materials", content_standard="B9.1.1.1 Matter",
        indicators=["B9.1.1.1.1 Identify materials"],
        indicator_codes=["B9.1.1.1.1"],
        lesson_topic="Original topic",
        introduction="Original introduction",
        main_activities=[{"phase": "MAIN", "description": "Original activity"}],
        assessment="Original assessment",
        conclusion="Original conclusion",
    )
    db.add(lp)
    db.commit()
    db.refresh(lp)
    return scheme, job, lp


class TestProtectedLessonFields:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("field,value", [
        ("school_id", "attacker-school"),
        ("owner_id", "attacker-user"),
        ("teacher_name", "Attacker"),
        ("school_name", "Attacker School"),
        ("subject", "Mathematics"),
        ("class_level", "Basic 1"),
        ("scheme_id", "other-scheme"),
        ("job_id", "other-job"),
        ("term", "Third Term"),
        ("strand", "Attacker strand"),
        ("content_standard", "Attacker standard"),
        ("week_number", 99),
        ("lesson_sequence", 99),
        ("lesson_date", date(2030, 1, 1)),
        ("template_id", "other-template"),
        ("source_occurrence_id", "attacker-occurrence"),
        ("indicators", ["B1.1.1.1.1 Hacked"]),
        ("indicator_codes", ["B1.1.1.1.1"]),
        ("source_tlrs", ["Attacker resource"]),
        ("status", "approved"),
        ("teacher_edited", False),
        ("duration_minutes", 999),
        ("created_at", date(2030, 1, 1)),
    ])
    async def test_protected_field_rejected_without_mutation(self, db, field, value):
        user = make_user(db)
        _scheme, _job, lp = _lesson(db, user, school_id=None)
        before = {
            "school_id": lp.school_id,
            "owner_id": lp.owner_id,
            "teacher_name": lp.teacher_name,
            "school_name": lp.school_name,
            "subject": lp.subject,
            "class_level": lp.class_level,
            "scheme_id": lp.scheme_id,
            "job_id": lp.job_id,
            "week_number": lp.week_number,
            "lesson_sequence": lp.lesson_sequence,
            "lesson_date": lp.lesson_date,
            "template_id": lp.template_id,
            "source_occurrence_id": lp.source_occurrence_id,
            "indicators": list(lp.indicators or []),
            "indicator_codes": list(lp.indicator_codes or []),
            "source_tlrs": list(lp.source_tlrs or []),
            "status": lp.status,
            "teacher_edited": lp.teacher_edited,
            "duration_minutes": lp.duration_minutes,
            "created_at": lp.created_at,
        }

        with pytest.raises(HTTPException) as exc:
            await generation.update_lesson_plan(
                lp.id, {field: value}, user, db)
        assert exc.value.status_code == 422
        assert field in str(exc.value.detail)

        db.refresh(lp)
        after = {
            "school_id": lp.school_id,
            "owner_id": lp.owner_id,
            "teacher_name": lp.teacher_name,
            "school_name": lp.school_name,
            "subject": lp.subject,
            "class_level": lp.class_level,
            "scheme_id": lp.scheme_id,
            "job_id": lp.job_id,
            "week_number": lp.week_number,
            "lesson_sequence": lp.lesson_sequence,
            "lesson_date": lp.lesson_date,
            "template_id": lp.template_id,
            "source_occurrence_id": lp.source_occurrence_id,
            "indicators": list(lp.indicators or []),
            "indicator_codes": list(lp.indicator_codes or []),
            "source_tlrs": list(lp.source_tlrs or []),
            "status": lp.status,
            "teacher_edited": lp.teacher_edited,
            "duration_minutes": lp.duration_minutes,
            "created_at": lp.created_at,
        }
        assert after == before

    def test_unknown_field_rejected_before_mutation(self, db):
        user = make_user(db)
        _scheme, _job, lp = _lesson(db, user)
        before_topic = lp.lesson_topic
        with pytest.raises(UnsupportedLessonFieldError) as exc:
            DataService().update_lesson_plan(
                db, lp.id, user.id,
                {"lesson_topic": "Should not persist", "arbitrary_property": 1})
        assert "arbitrary_property" in str(exc.value)
        db.refresh(lp)
        assert lp.lesson_topic == before_topic


class TestAllowedLessonEdits:
    @pytest.mark.asyncio
    async def test_owner_can_edit_permitted_fields_and_reload(self, db):
        user = make_user(db)
        _scheme, _job, lp = _lesson(db, user)
        payload = {
            "lesson_topic": "Edited topic",
            "introduction": "Edited introduction",
            "starter_activity": "Edited starter",
            "assessment": "Edited assessment",
            "conclusion": "Edited conclusion",
            "class_assignment": "In-class work",
            "home_assignment": "Home work",
            "homework": "Home work",
            "keywords": ["matter", "materials"],
            "teaching_learning_resources": ["Chart", "Samples"],
            "structured_references": [
                {"type": "Textbook", "title": "Science Book", "page": "12"}
            ],
            "main_activities": [
                {"phase": "MAIN", "description": "Edited activity",
                 "duration_minutes": 25, "resources": ["Chart"]}
            ],
        }
        updated = await generation.update_lesson_plan(lp.id, payload, user, db)
        assert updated["lesson_topic"] == "Edited topic"
        assert updated["main_activities"][0]["description"] == "Edited activity"

        db.expire_all()
        stored = db.query(LessonPlanDB).filter(LessonPlanDB.id == lp.id).one()
        assert stored.lesson_topic == "Edited topic"
        assert stored.introduction == "Edited introduction"
        assert stored.main_activities[0]["duration_minutes"] == 25
        assert stored.keywords == ["matter", "materials"]
        assert stored.teacher_edited is True

    def test_valid_edit_survives_docx_export(self, db):
        user = make_user(db)
        scheme, job, lp = _lesson(db, user)
        DataService().update_lesson_plan(
            db, lp.id, user.id,
            {"assessment": "Export-visible edited assessment"})
        response = __import__("asyncio").run(
            generation.export_docx(job.id, user=user, db=db))
        document = Document(response.path)
        text = "\n".join(p.text for p in document.paragraphs)
        text += "\n" + "\n".join(
            cell.text for table in document.tables for row in table.rows
            for cell in row.cells)
        assert "Export-visible edited assessment" in text

    @pytest.mark.asyncio
    async def test_non_list_activity_is_refused_without_mutation(self, db):
        user = make_user(db)
        _scheme, _job, lp = _lesson(db, user)
        before = list(lp.main_activities or [])
        await generation.update_lesson_plan(
            lp.id, {"main_activities": "not-a-list"}, user, db)
        db.refresh(lp)
        assert (lp.main_activities or []) == before

    @pytest.mark.asyncio
    async def test_invalid_nested_activity_is_refused_without_partial_write(self, db):
        user = make_user(db)
        _scheme, _job, lp = _lesson(db, user)
        before = list(lp.main_activities or [])
        await generation.update_lesson_plan(
            lp.id,
            {"main_activities": [
                {"phase": "MAIN", "description": "Valid"},
                {"phase": "MAIN", "description": 123},
            ]},
            user, db)
        db.refresh(lp)
        assert (lp.main_activities or []) == before

    @pytest.mark.asyncio
    async def test_user_b_cannot_modify_user_a_lesson(self, db):
        user_a = make_user(db, email="a@lesson.test")
        user_b = make_user(db, email="b@lesson.test")
        _scheme, _job, lp = _lesson(db, user_a)
        with pytest.raises(HTTPException) as exc:
            await generation.update_lesson_plan(
                lp.id, {"assessment": "hijacked"}, user_b, db)
        assert exc.value.status_code in (403, 404)
        db.refresh(lp)
        assert lp.assessment == "Original assessment"


def test_allowlist_is_a_strict_subset_of_lesson_columns():
    from src.database import LessonPlanDB
    from src.service import LESSON_EDITABLE_FIELDS

    columns = {c.name for c in LessonPlanDB.__table__.columns}
    assert LESSON_EDITABLE_FIELDS <= columns
    protected = {
        "id", "job_id", "owner_id", "scheme_id", "school_id",
        "week_number", "lesson_sequence", "lesson_date", "class_level",
        "subject", "school_name", "teacher_name", "template_id", "status",
        "teacher_edited", "created_at", "source_occurrence_id",
        "indicators", "indicator_codes", "source_tlrs",
    }
    assert LESSON_EDITABLE_FIELDS.isdisjoint(protected)


def test_allowlist_covers_frontend_payload_keys():
    """Pin the actual teacher-editable payload; protected keys stay out."""
    allowed = normalize_lesson_updates({
        "lesson_topic": "t", "introduction": "i", "starter_activity": "s",
        "assessment": "a", "conclusion": "c", "class_assignment": "ca",
        "home_assignment": "ha", "homework": "hw", "keywords": ["k"],
        "teaching_learning_resources": ["r"], "structured_references": [],
        "wapef_deep_hope": "", "wapef_storyline": "", "wapef_through_lines": [],
        "wapef_gods_story": "", "main_activities": [],
        "learner_activities": [], "teacher_activities": [],
        "learning_objectives": [], "other_tlrs": [], "core_competencies": [],
        "references": [], "differentiation": "", "remarks": "",
    })
    assert set(allowed) == {
        "lesson_topic", "introduction", "starter_activity", "assessment",
        "conclusion", "class_assignment", "home_assignment", "homework",
        "keywords", "teaching_learning_resources", "structured_references",
        "wapef_deep_hope", "wapef_storyline", "wapef_through_lines",
        "wapef_gods_story", "main_activities", "learner_activities",
        "teacher_activities", "learning_objectives", "other_tlrs",
        "core_competencies", "references", "differentiation", "remarks",
    }

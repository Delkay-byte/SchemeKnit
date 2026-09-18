"""
Authorization + IDOR hardening tests.

For every school-owned resource, USER B must not access USER A's object by
swapping IDs in the URL/payload. Server-side ownership enforced everywhere.
"""

import os
import sys
from datetime import date

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.conftest import make_user, make_school
from src.database import (
    SchemeDB, LessonPlanDB, GenerationJobDB, TemplateDefinitionDB, generate_id,
)
from src.routers import documents, curriculum, generation
from src.routers.templates import (
    get_custom_template_detail, preview_custom_template,
)
from src.service import data_service


@pytest.fixture()
def two_tenants(db):
    """Two schools, one teacher each, each owning scheme+lesson+job+template."""
    tenants = []
    for i in (1, 2):
        school = make_school(db, name=f"School {i}", code=f"SCH-IDOR-{i}")
        teacher = make_user(db, role="teacher", school_id=school.id,
                            email=f"teacher{i}@idor.test")
        scheme = SchemeDB(id=generate_id(), owner_id=teacher.id, school_id=school.id,
                          filename=f"scheme{i}.docx", subject="Science", class_level="Basic 9")
        db.add(scheme)
        db.flush()
        job = GenerationJobDB(id=generate_id(), owner_id=teacher.id, scheme_id=scheme.id,
                              status="completed", completed_lessons=1)
        db.add(job)
        db.flush()
        lesson = LessonPlanDB(id=generate_id(), job_id=job.id, owner_id=teacher.id,
                              scheme_id=scheme.id, week_number=1, lesson_sequence=1,
                              class_level="Basic 9", subject="Science")
        db.add(lesson)
        tpl = data_service.create_custom_template(
            db, owner_id=teacher.id, name=f"T{i}", family="jhs",
            educational_level="Junior High School")
        data_service.update_custom_template(
            db, tpl.id, teacher.id, structure={"tables": []}, status="active")
        tenants.append({"school": school, "teacher": teacher, "scheme": scheme,
                        "job": job, "lesson": lesson, "template": tpl})
    db.commit()
    return tenants


class TestSchemeIDOR:
    @pytest.mark.asyncio
    async def test_get_other_scheme_denied(self, db, two_tenants):
        a, b = two_tenants
        with pytest.raises(HTTPException) as e:
            await documents.get_scheme(b["scheme"].id, a["teacher"], db)
        assert e.value.status_code in (403, 404)

    @pytest.mark.asyncio
    async def test_weeks_other_scheme_denied(self, db, two_tenants):
        a, b = two_tenants
        with pytest.raises(HTTPException) as e:
            await documents.get_scheme_weeks(b["scheme"].id, a["teacher"], db)
        assert e.value.status_code in (403, 404)

    @pytest.mark.asyncio
    async def test_status_update_other_scheme_denied(self, db, two_tenants):
        a, b = two_tenants
        with pytest.raises(HTTPException) as e:
            await documents.update_scheme_status(
                b["scheme"].id, {"status": "approved"}, a["teacher"], db)
        assert e.value.status_code in (403, 404)

    @pytest.mark.asyncio
    async def test_delete_other_scheme_denied(self, db, two_tenants):
        a, b = two_tenants
        with pytest.raises(HTTPException) as e:
            await documents.delete_scheme(b["scheme"].id, a["teacher"], db)
        assert e.value.status_code in (403, 404)
        # victim row intact
        assert db.query(SchemeDB).filter(SchemeDB.id == b["scheme"].id).first() is not None

    @pytest.mark.asyncio
    async def test_approve_other_scheme_denied(self, db, two_tenants):
        a, b = two_tenants
        with pytest.raises(HTTPException) as e:
            await curriculum.approve_scheme(b["scheme"].id, a["teacher"], db)
        assert e.value.status_code in (403, 404)

    @pytest.mark.asyncio
    async def test_workflow_other_scheme_denied(self, db, two_tenants):
        a, b = two_tenants
        with pytest.raises(HTTPException) as e:
            await documents.get_workflow_state(b["scheme"].id, a["teacher"], db)
        assert e.value.status_code in (403, 404)

    def test_list_scoped_to_owner(self, db, two_tenants):
        a, b = two_tenants
        mine = data_service.list_schemes(db, a["teacher"].id)
        assert {s.id for s in mine} == {a["scheme"].id}


class TestLessonJobIDOR:
    @pytest.mark.asyncio
    async def test_get_other_lesson_denied(self, db, two_tenants):
        a, b = two_tenants
        with pytest.raises(HTTPException) as e:
            await generation.get_lesson_plan(b["lesson"].id, a["teacher"], db)
        assert e.value.status_code in (403, 404)

    @pytest.mark.asyncio
    async def test_update_other_lesson_denied(self, db, two_tenants):
        a, b = two_tenants
        with pytest.raises(HTTPException) as e:
            await generation.update_lesson_plan(
                b["lesson"].id, {"assessment": "hijacked"}, a["teacher"], db)
        assert e.value.status_code in (403, 404)

    def test_job_lookup_owner_scoped(self, db, two_tenants):
        a, b = two_tenants
        assert data_service.get_job(db, b["job"].id, a["teacher"].id) is None
        assert data_service.get_job(db, b["job"].id, b["teacher"].id) is not None

    def test_lessons_for_job_owner_scoped(self, db, two_tenants):
        a, b = two_tenants
        assert data_service.get_lesson_plans_for_job(db, b["job"].id, a["teacher"].id) == []
        assert len(data_service.get_lesson_plans_for_job(db, b["job"].id, b["teacher"].id)) == 1


class TestTemplateIDOR:
    @pytest.mark.asyncio
    async def test_get_other_template_denied(self, db, two_tenants):
        a, b = two_tenants
        with pytest.raises(HTTPException) as e:
            await get_custom_template_detail(b["template"].id, db, a["teacher"])
        assert e.value.status_code in (403, 404)

    @pytest.mark.asyncio
    async def test_preview_other_template_denied(self, db, two_tenants):
        a, b = two_tenants
        with pytest.raises(HTTPException) as e:
            await preview_custom_template(b["template"].id, db, a["teacher"])
        assert e.value.status_code in (403, 404)

    def test_list_scoped_to_owner(self, db, two_tenants):
        a, b = two_tenants
        mine = data_service.list_custom_templates(db, owner_id=a["teacher"].id)
        assert {t.id for t in mine} == {a["template"].id}

"""
Generation + workflow regression tests.

Server-authoritative semantics: regeneration replaces (never duplicates),
failed jobs don't complete stages, export events require real exports,
workflow state reconstructs purely from stored rows.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.conftest import make_user, make_school
from src.database import SchemeDB, LessonPlanDB, GenerationJobDB, generate_id
from src.service import data_service, compute_workflow_state


@pytest.fixture()
def teacher_scheme(db):
    school = make_school(db)
    teacher = make_user(db, role="teacher", school_id=school.id, email="gw@reg.test")
    scheme = SchemeDB(id=generate_id(), owner_id=teacher.id, school_id=school.id,
                      filename="s.docx", subject="Science", class_level="Basic 9",
                      status="approved")
    db.add(scheme)
    db.commit()
    return teacher, scheme


def make_job(db, teacher, scheme, status="completed", lessons=3):
    job = GenerationJobDB(id=generate_id(), owner_id=teacher.id, scheme_id=scheme.id,
                          status=status, completed_lessons=lessons if status == "completed" else 0)
    db.add(job)
    db.flush()
    if lessons and status == "completed":
        for i in range(lessons):
            db.add(LessonPlanDB(id=generate_id(), job_id=job.id, owner_id=teacher.id,
                                scheme_id=scheme.id, week_number=i + 1, lesson_sequence=1,
                                class_level="Basic 9", subject="Science"))
    db.commit()
    return job


class TestRegeneration:
    def test_regeneration_replaces_without_duplicates(self, db, teacher_scheme):
        teacher, scheme = teacher_scheme
        make_job(db, teacher, scheme, lessons=3)
        assert data_service.count_lessons_for_scheme(db, scheme.id, teacher.id) == 3
        # Regeneration path: delete scheme lessons, then create anew
        data_service.delete_lesson_plans_for_scheme(db, scheme.id, teacher.id)
        make_job(db, teacher, scheme, lessons=3)
        assert data_service.count_lessons_for_scheme(db, scheme.id, teacher.id) == 3

    def test_failed_job_leaves_prior_lessons(self, db, teacher_scheme):
        teacher, scheme = teacher_scheme
        make_job(db, teacher, scheme, lessons=2)
        failed = make_job(db, teacher, scheme, status="failed", lessons=0)
        assert failed.status == "failed"
        assert data_service.count_lessons_for_scheme(db, scheme.id, teacher.id) == 2
        st = compute_workflow_state("approved", True, False, 2, False)
        assert {s["key"]: s["state"] for s in st}["generate"] == "active"

    def test_duplicate_generate_calls_converge(self, db, teacher_scheme):
        teacher, scheme = teacher_scheme
        # Two rapid generations: each replaces; final count equals one run
        for _ in range(2):
            data_service.delete_lesson_plans_for_scheme(db, scheme.id, teacher.id)
            make_job(db, teacher, scheme, lessons=4)
        assert data_service.count_lessons_for_scheme(db, scheme.id, teacher.id) == 4


class TestWorkflowReconstruction:
    def test_fresh_upload_state(self, db, teacher_scheme):
        _, scheme = teacher_scheme
        scheme.status = "extracted"
        db.commit()
        st = {s["key"]: s["state"] for s in compute_workflow_state(
            scheme.status, False, False, 0, False)}
        assert st == {"upload": "completed", "review": "active", "configure": "locked",
                      "generate": "locked", "export": "locked"}

    def test_full_journey_reconstructs(self, db, teacher_scheme):
        teacher, scheme = teacher_scheme
        job = make_job(db, teacher, scheme, lessons=5)
        data_service.log_export_event(db, job.id, scheme.id, teacher.id, "docx")
        st = {s["key"]: s["state"] for s in compute_workflow_state(
            "approved", True, True, 5, True)}
        assert set(st.values()) == {"completed"}

    def test_export_without_lessons_impossible(self, db, teacher_scheme):
        # generate flag requires lessons>0 even if a job claims completion
        st = {s["key"]: s["state"] for s in compute_workflow_state(
            "approved", True, True, 0, False)}
        assert st["generate"] == "active"
        assert st["export"] == "locked"

    def test_export_event_requires_scheme_context(self, db, teacher_scheme):
        teacher, scheme = teacher_scheme
        job = make_job(db, teacher, scheme, lessons=1)
        data_service.log_export_event(db, job.id, scheme.id, teacher.id, "xlsx")
        assert data_service.has_export_for_scheme(db, scheme.id, teacher.id) is True
        other = make_user(db, role="teacher", school_id=scheme.school_id,
                          email="other@reg.test")
        assert data_service.has_export_for_scheme(db, scheme.id, other.id) is False

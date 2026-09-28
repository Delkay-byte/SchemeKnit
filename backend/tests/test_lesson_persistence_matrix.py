"""
Persistence matrix (PART 4/5/22/36).

Every teacher-owned lesson field must survive save -> reload -> export-model
conversion, and the Save Review draft payload must persist a complete
realistic payload with no 500. A field the UI can edit but the save path
drops is a data-loss defect, not a cosmetic one.
"""

from datetime import date

import pytest


APPROVED_DEEP_HOPE = (
    "Learners will recognize and appreciate the beauty, order, and purpose "
    "of design in the physical world around them."
)


def _app(db, user, require_user):
    """Minimal app with the generation router and auth/db overridden."""
    from fastapi import FastAPI
    from src.auth import get_current_user, require_teacher_workflow
    from src.database import get_db
    from src.routers import generation as gen_router

    app = FastAPI()
    app.include_router(gen_router.router, prefix="/api/generation")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_teacher_workflow] = lambda: require_user
    app.dependency_overrides[get_db] = lambda: db
    return app


def _login(db):
    from tests.conftest import make_user

    # Both auth dependencies are overridden on the test app, so no
    # entitlement setup is required for these save-path tests.
    return make_user(db, role="teacher", email="persist-matrix@t.test")


class TestCompleteSaveRoundtrip:
    """PUT -> GET must echo every teacher-owned field verbatim."""

    def test_complete_save_payload_roundtrips(self, db):
        from fastapi.testclient import TestClient
        from tests.test_export_download import make_job_with_lessons

        user = _login(db)
        _scheme, job = make_job_with_lessons(db, user, lessons=1)
        from src.database import LessonPlanDB
        lp = db.query(LessonPlanDB).filter_by(job_id=job.id).first()

        payload = {
            "lesson_topic": "Roundtrip Topic",
            "introduction": "Intro R",
            "assessment": "Assess R",
            "conclusion": "Concl R",
            "starter_activity": "RT starter",
            "differentiation": "RT differentiation",
            "keywords": ["kw-one", "kw-two"],
            "other_tlrs": ["Chart of atoms"],
            "core_competencies": ["Critical Thinking and Problem Solving"],
            "structured_references": [{
                "type": "Textbook", "title": "RT Book",
                "author_publisher": "RT Pub", "page": "5", "notes": "n",
            }],
            "references": ["RT Book"],
            "essential_questions": ["What if we change the material?"],
            "homework": "Take-home: complete the worksheet.",
            "class_assignment": "In-class: sort the samples in pairs.",
            "home_assignment": "At-home: find three examples at home.",
            "duration_minutes": 75,
            "school_name": "RT School",
            "template_id": "tpl-wapef-approved-plan",
            "remarks": "RT remarks",
            "main_activities": [
                {"phase": "main_learning", "description": "RT activity",
                 "duration_minutes": 20, "resources": ["Board"]},
            ],
        }
        with TestClient(_app(db, user, user)) as client:
            r = client.put(f"/api/generation/lessons/{lp.id}", json=payload)
            assert r.status_code == 200, r.text
            g = client.get(f"/api/generation/lessons/{lp.id}")
            assert g.status_code == 200, g.text

        got = g.json()
        for key, expected in payload.items():
            if key == "main_activities":
                continue
            assert got.get(key) == expected, (
                f"field {key!r} lost on save: {got.get(key)!r} != {expected!r}")
        acts = [
            {"phase": a.get("phase"), "description": a.get("description"),
             "duration_minutes": a.get("duration_minutes"),
             "resources": a.get("resources") or []}
            for a in got.get("main_activities") or []
        ]
        assert acts == payload["main_activities"]

    def test_save_survives_a_fresh_session_reload(self, db, db_engine):
        """The write must be durable: a NEW session (not the write session)
        reads back every field (the save-then-reload browser flow)."""
        from sqlalchemy.orm import sessionmaker
        from fastapi.testclient import TestClient
        from tests.test_export_download import make_job_with_lessons

        user = _login(db)
        _scheme, job = make_job_with_lessons(db, user, lessons=1)
        from src.database import LessonPlanDB
        lp = db.query(LessonPlanDB).filter_by(job_id=job.id).first()
        updates = {
            "homework": "Home task persists",
            "class_assignment": "Class task persists",
            "home_assignment": "Evening task persists",
            "template_id": "tpl-official-ges-nacca-jhs",
            "duration_minutes": 45,
            "school_name": "Reload School",
            "keywords": ["persist"],
        }
        with TestClient(_app(db, user, user)) as client:
            r = client.put(f"/api/generation/lessons/{lp.id}", json=updates)
            assert r.status_code == 200, r.text

        Session = sessionmaker(bind=db_engine)
        fresh = Session()
        try:
            row = fresh.query(LessonPlanDB).filter_by(id=lp.id).first()
            assert row.homework == "Home task persists"
            assert row.class_assignment == "Class task persists"
            assert row.home_assignment == "Evening task persists"
            assert row.template_id == "tpl-official-ges-nacca-jhs"
            assert row.duration_minutes == 45
            assert row.school_name == "Reload School"
            assert list(row.keywords or []) == ["persist"]
        finally:
            fresh.close()

    def test_alias_and_type_coercion_at_save_boundary(self, db):
        """duration/school aliases land on the canonical columns and a
        numeric string becomes an int (never text in an int column)."""
        from fastapi.testclient import TestClient
        from tests.test_export_download import make_job_with_lessons

        user = _login(db)
        _scheme, job = make_job_with_lessons(db, user, lessons=1)
        from src.database import LessonPlanDB
        lp = db.query(LessonPlanDB).filter_by(job_id=job.id).first()

        with TestClient(_app(db, user, user)) as client:
            r = client.put(f"/api/generation/lessons/{lp.id}",
                           json={"duration": "45", "school": "Alias School",
                                 "class_size": "31"})
            assert r.status_code == 200, r.text
            got = r.json()
        assert got["duration_minutes"] == 45
        assert got["school_name"] == "Alias School"
        assert got["class_size"] == 31

    def test_assignment_fields_coerce_lists_to_text(self, db):
        """A list sent to a text column stores joined text, never a
        Python-list repr."""
        from fastapi.testclient import TestClient
        from tests.test_export_download import make_job_with_lessons

        user = _login(db)
        _scheme, job = make_job_with_lessons(db, user, lessons=1)
        from src.database import LessonPlanDB
        lp = db.query(LessonPlanDB).filter_by(job_id=job.id).first()

        with TestClient(_app(db, user, user)) as client:
            r = client.put(f"/api/generation/lessons/{lp.id}",
                           json={"class_assignment": ["Task one", "Task two"],
                                 "home_assignment": None})
            assert r.status_code == 200, r.text
            got = r.json()
        assert got["class_assignment"] == "Task one; Task two"
        assert got["home_assignment"] == ""

    def test_ownership_fields_are_not_overwritable(self, db):
        """A crafted payload cannot reassign id/owner/scheme/job."""
        from fastapi.testclient import TestClient
        from tests.test_export_download import make_job_with_lessons

        user = _login(db)
        _scheme, job = make_job_with_lessons(db, user, lessons=1)
        from src.database import LessonPlanDB
        lp = db.query(LessonPlanDB).filter_by(job_id=job.id).first()
        original = (lp.id, lp.owner_id, lp.scheme_id, lp.job_id)

        with TestClient(_app(db, user, user)) as client:
            r = client.put(f"/api/generation/lessons/{lp.id}",
                           json={"id": "hijack", "owner_id": "evil",
                                 "scheme_id": "evil", "job_id": "evil"})
            assert r.status_code == 200, r.text
            got = r.json()
        assert (got["id"], got.get("scheme_id"), got.get("job_id")) == (
            original[0], original[2], original[3])
        db.refresh(lp)
        assert (lp.id, lp.owner_id, lp.scheme_id, lp.job_id) == original


class TestSaveReviewCompletePayload:
    """Save Review (PUT lesson-review) with a complete realistic payload:
    200 on save, drafts readable back, no 500 (regression for the reported
    'Action failed / Internal server error')."""

    def _drafts(self):
        drafts = {}
        for i in range(6):
            drafts[str(i)] = {
                "period": f"Monday - Period {i + 1}",
                "keywords": [f"kw{i}", f"term{i}"],
                "other_tlrs": ["Chart"],
                "core_competencies": ["Critical Thinking and Problem Solving"],
                "structured_references": [
                    {"type": "Textbook", "title": "Basic 9 ICT",
                     "author_publisher": "CPD", "page": str(10 + i),
                     "notes": ""},
                    {"type": "Curriculum", "title": "Computing Curriculum",
                     "author_publisher": "NaCCA", "page": "", "notes": ""},
                    {"type": "Other", "title": "", "page": ""},
                ],
                "wapef_deep_hope": APPROVED_DEEP_HOPE,
                "wapef_storyline": "Shaping our world.",
                "wapef_through_lines": ["God worshiper", "Earth keeper"],
                "wapef_gods_story": "Creation",
                "remarks": f"Remark {i}",
            }
        return drafts

    def test_complete_review_payload_saves_and_reads_back(self, db):
        from fastapi.testclient import TestClient
        from tests.test_export_download import make_job_with_lessons

        user = _login(db)
        scheme, _job = make_job_with_lessons(db, user, lessons=1)
        drafts = self._drafts()

        with TestClient(_app(db, user, user)) as client:
            put = client.put(f"/api/generation/{scheme.id}/lesson-review",
                             json={"drafts": drafts})
            assert put.status_code == 200, put.text
            get = client.get(f"/api/generation/{scheme.id}/lesson-review")
            assert get.status_code == 200, get.text

        saved = get.json()["drafts"]
        for key, expected in drafts.items():
            got = saved.get(key)
            assert got is not None, f"draft row {key} missing after save"
            for field, value in expected.items():
                assert got.get(field) == value, (
                    f"row {key} field {field!r}: {got.get(field)!r} != {value!r}")

    def test_review_payload_with_every_allowed_key(self, db):
        """All ten allowed review-draft keys persist together."""
        from fastapi.testclient import TestClient
        from tests.test_export_download import make_job_with_lessons

        user = _login(db)
        scheme, _job = make_job_with_lessons(db, user, lessons=1)
        row = {
            "keywords": ["a"], "other_tlrs": ["b"],
            "core_competencies": ["c"], "structured_references": [],
            "wapef_deep_hope": APPROVED_DEEP_HOPE,
            "wapef_storyline": "Shaping our world.",
            "wapef_through_lines": ["Image reflector"],
            "wapef_gods_story": "Redemption",
            "remarks": "r", "period": "Tuesday - Period 2",
        }
        with TestClient(_app(db, user, user)) as client:
            put = client.put(f"/api/generation/{scheme.id}/lesson-review",
                             json={"drafts": {"3": row}})
            assert put.status_code == 200, put.text
            got = client.get(
                f"/api/generation/{scheme.id}/lesson-review").json()["drafts"]
        assert set(got["3"].keys()) == set(row.keys())
        for k, v in row.items():
            assert got["3"][k] == v


class TestWapefFirstClassPersistence:
    """PART 6/22: approved WAPEF selections survive create -> save -> reload
    -> export-model conversion verbatim (never rewritten, never dropped)."""

    def test_approved_wapef_values_roundtrip(self, db):
        from fastapi.testclient import TestClient
        from tests.test_export_download import make_job_with_lessons

        user = _login(db)
        _scheme, job = make_job_with_lessons(db, user, lessons=1)
        from src.database import LessonPlanDB
        lp = db.query(LessonPlanDB).filter_by(job_id=job.id).first()

        selection = {
            "wapef_deep_hope": APPROVED_DEEP_HOPE,
            "wapef_storyline": "Shaping our world.",
            "wapef_through_lines": ["God worshiper", "Earth keeper",
                                    "Beauty creator"],
            "wapef_gods_story": "Creation",
            "remarks": "Teacher remarks survive.",
        }
        with TestClient(_app(db, user, user)) as client:
            r = client.put(f"/api/generation/lessons/{lp.id}", json=selection)
            assert r.status_code == 200, r.text
            again = client.get(f"/api/generation/lessons/{lp.id}").json()

        for k, v in selection.items():
            assert again.get(k) == v, f"{k} not persisted: {again.get(k)!r}"

    def test_wapef_and_assignments_reach_the_export_model(self, db):
        """The DOCX/PDF render path converts rows through _db_to_lesson_model;
        WAPEF, homework, assignments and template_id must be on that model."""
        from tests.test_export_download import make_job_with_lessons
        from src.routers.generation import _db_to_lesson_model, _serialize_lesson
        from src.database import LessonPlanDB

        user = _login(db)
        scheme, job = make_job_with_lessons(db, user, lessons=1)
        lp = db.query(LessonPlanDB).filter_by(job_id=job.id).first()
        lp.wapef_deep_hope = APPROVED_DEEP_HOPE
        lp.wapef_gods_story = "Fall"
        lp.wapef_through_lines = ["Justice seeker"]
        lp.homework = "Export homework"
        lp.class_assignment = "Export class work"
        lp.home_assignment = "Export home work"
        lp.template_id = "tpl-official-ges-nacca-jhs"
        db.commit()
        db.refresh(lp)

        model = _db_to_lesson_model(lp)
        assert model.wapef_deep_hope == APPROVED_DEEP_HOPE
        assert model.wapef_gods_story == "Fall"
        assert model.wapef_through_lines == ["Justice seeker"]
        assert model.homework == "Export homework"
        assert model.class_assignment == "Export class work"
        assert model.home_assignment == "Export home work"
        assert model.template_id == "tpl-official-ges-nacca-jhs"

        ser = _serialize_lesson(lp, scheme)
        assert ser["homework"] == "Export homework"
        assert ser["class_assignment"] == "Export class work"
        assert ser["home_assignment"] == "Export home work"
        assert ser["template_id"] == "tpl-official-ges-nacca-jhs"
        assert ser["wapef_deep_hope"] == APPROVED_DEEP_HOPE


class TestCreatePathPersistsNewFields:
    """Generation-created rows carry template_id and assignment fields."""

    def test_create_lesson_plan_writes_template_and_assignments(self, db):
        from tests.conftest import make_user
        from tests.test_export_download import make_job_with_lessons
        from src.models import LessonPlan, ClassLevel, Subject, LessonStatus
        from src.service import DataService
        from src.database import LessonPlanDB

        user = make_user(db, role="teacher", email="create-persist@t.test")
        scheme, job = make_job_with_lessons(db, user, lessons=0)
        svc = DataService()
        lp = LessonPlan(
            scheme_of_work_id=scheme.id,
            term_config_id=job.id,
            week_number=1,
            lesson_sequence=1,
            lesson_date=date(2026, 10, 5),
            class_level=ClassLevel.BASIC_9,
            subject=Subject.ICT,
            lesson_topic="Creation topic",
            class_assignment="Guided practice task",
            home_assignment="Take-home task",
            homework="Legacy homework field",
            template_id="tpl-wapef-approved-plan",
            status=LessonStatus.GENERATED,
        )
        created = svc.create_lesson_plan(db, user.id, job.id, scheme.id, lp)
        db.refresh(created)
        assert created.template_id == "tpl-wapef-approved-plan"
        assert created.class_assignment == "Guided practice task"
        assert created.home_assignment == "Take-home task"
        assert created.homework == "Legacy homework field"

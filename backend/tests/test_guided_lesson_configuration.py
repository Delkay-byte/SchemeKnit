"""Phase 11 — guided lesson configuration (Phase 2/3) API regression tests.

Everything here is a real round trip through the FastAPI ASGI app — the same
path a browser takes:

* GET  /api/generation/{id}/lesson-config prepopulates from the teacher's
  profile and preferences, and reports readiness (never invents values).
* PUT  /api/generation/{id}/lesson-config validates field-by-field and
  persists per plan (never touching global school settings).
* Generation refuses to start while REQUIRED configuration is missing.
* A saved configuration survives reload and is scoped to its plan.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.auth import create_access_token, hash_password  # noqa: E402
from src.database import Base, get_db, generate_id, SchemeDB, User  # noqa: E402
from src.main import app  # noqa: E402
from tests.conftest import make_school, make_product_plan, make_license  # noqa: E402


FULL_CONFIG = {
    "school_name": "Kpogede Community School",
    "teacher_name": "Saviour Amegayie",
    "class_size": 31,
    "reference": "Basic 9 Science Curriculum (NaCCA)",
    "lesson_duration_minutes": 60,
    "periods_per_week": 3,
    "period": "1st & 2nd",
    "teaching_days": [0, 2, 4],
}


@pytest.fixture
def http(tmp_path, monkeypatch):
    """A TestClient whose app shares ONE in-memory SQLite connection.

    Same pattern as test_web_acceptance_http: a StaticPool pins every thread
    to one connection so synchronous (threadpool) endpoints see the data.
    """
    monkeypatch.setenv("TEACHFLOW_DATA_DIR", str(tmp_path / "data"))

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    def _override_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_db
    client = TestClient(app)

    school = make_school(db)
    plan = make_product_plan(db)
    make_license(db, school.id, plan.id, status="active")
    user = User(
        id=generate_id(), email="guided-config@t.test", full_name="Guided Teacher",
        hashed_password=hash_password("Strong1!Pass"), school_name=school.name,
        is_active=True, role="teacher", school_id=school.id,
    )
    db.add(user)
    db.commit()
    token = create_access_token({"sub": user.id, "role": user.role})
    client.headers.update({"Authorization": f"Bearer {token}"})

    def _scheme():
        s = SchemeDB(
            id=generate_id(), owner_id=user.id, school_id=school.id,
            filename="BASIC 9 SCIENCE SCHEME OF LEARNING.docx",
            subject="Science", class_level="Basic 9", term="First Term",
        )
        db.add(s)
        db.commit()
        db.refresh(s)
        return s

    client.scheme_factory = _scheme  # type: ignore[attr-defined]
    yield client
    app.dependency_overrides.pop(get_db, None)
    db.close()
    engine.dispose()


class TestLessonConfigEndpoints:
    def test_get_prepopulates_from_profile_and_reports_missing(self, http):
        scheme = http.scheme_factory()
        resp = http.get(f"/api/generation/{scheme.id}/lesson-config")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # Prepopulated from the authenticated user's school relationship —
        # never invented by the form.
        assert body["config"]["school_name"] == "Test School"
        assert body["config"]["teacher_name"] == "Guided Teacher"
        # Required fields with no saved value are reported, not defaulted.
        assert "class_size" in body["missing"]
        assert "teaching_days" in body["missing"]
        assert body["ready"] is False
        assert "class_size" in body["required_fields"]

    def test_put_validates_and_persists_per_plan(self, http):
        scheme = http.scheme_factory()
        resp = http.put(f"/api/generation/{scheme.id}/lesson-config",
                        json=FULL_CONFIG)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["config"]["class_size"] == 31
        assert body["config"]["teaching_days"] == [0, 2, 4]
        assert body["ready"] is True
        assert body["missing"] == []
        # Persisted on the scheme row — a reload returns the same values.
        resp2 = http.get(f"/api/generation/{scheme.id}/lesson-config")
        assert resp2.json()["config"]["class_size"] == 31
        assert resp2.json()["ready"] is True

    def test_put_rejects_nonsense_values_with_field_errors(self, http):
        scheme = http.scheme_factory()
        bad = dict(FULL_CONFIG, class_size=0, lesson_duration_minutes=5,
                   teaching_days=[0, 6])
        resp = http.put(f"/api/generation/{scheme.id}/lesson-config", json=bad)
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert "Class size" in detail
        assert "duration" in detail
        assert "weekdays" in detail

    def test_put_keeps_optional_fields_blank_when_not_supplied(self, http):
        scheme = http.scheme_factory()
        resp = http.put(
            f"/api/generation/{scheme.id}/lesson-config",
            json={"school_name": "Test School", "teacher_name": "Guided Teacher",
                  "class_size": 24, "lesson_duration_minutes": 60,
                  "teaching_days": [1, 3]})
        assert resp.status_code == 200, resp.text
        config = resp.json()["config"]
        # Reference and period legitimately stay blank — never manufactured.
        assert "reference" not in config
        assert "period" not in config

    def test_saved_config_is_scoped_to_its_plan(self, http):
        scheme_a = http.scheme_factory()
        scheme_b = http.scheme_factory()
        http.put(f"/api/generation/{scheme_a.id}/lesson-config", json=FULL_CONFIG)
        # Plan B never inherits plan A's values silently.
        resp = http.get(f"/api/generation/{scheme_b.id}/lesson-config")
        assert resp.json()["config"].get("class_size") is None
        assert resp.json()["ready"] is False


class TestGenerationConfigGate:
    def test_generate_without_required_configuration_is_refused(self, http):
        """Generation cannot start while required configuration is missing.

        The scheme is subject/class-complete (no 409 from those gates), but no
        lesson configuration was ever saved and the request omits class_size —
        the guided configuration step must be completed first.
        """
        scheme = http.scheme_factory()
        payload = {
            "scheme_of_work_id": scheme.id,
            "class_level": "Basic 9", "subject": "Science",
            "term_start_date": "2026-09-08", "term_end_date": "2026-12-18",
            "lessons_per_week": 2, "lesson_duration_minutes": 60,
            "teaching_days": [0, 2], "holidays": [], "ai_mode": "OFF",
            "class_size": None,
        }
        resp = http.post(f"/api/generation/{scheme.id}/generate", json=payload)
        assert resp.status_code == 409, resp.text
        assert "lesson configuration" in resp.json()["detail"].lower()

    def test_saved_configuration_survives_reload(self, http):
        """Configuration persists across navigation and reload (Phase 2.3)."""
        scheme = http.scheme_factory()
        http.put(f"/api/generation/{scheme.id}/lesson-config", json=FULL_CONFIG)
        first = http.get(f"/api/generation/{scheme.id}/lesson-config").json()
        second = http.get(f"/api/generation/{scheme.id}/lesson-config").json()
        assert first["config"] == second["config"]
        assert first["ready"] is True

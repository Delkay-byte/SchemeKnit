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
from src.models import TermConfig  # noqa: E402
from src.routers.generation import _apply_saved_lesson_config  # noqa: E402
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
        assert resp.status_code == 422, resp.text
        body = resp.json()
        detail = body.get("detail")
        assert "lesson configuration" in str(detail).lower()

    def test_saved_configuration_survives_reload(self, http):
        """Configuration persists across navigation and reload (Phase 2.3)."""
        scheme = http.scheme_factory()
        http.put(f"/api/generation/{scheme.id}/lesson-config", json=FULL_CONFIG)
        first = http.get(f"/api/generation/{scheme.id}/lesson-config").json()
        second = http.get(f"/api/generation/{scheme.id}/lesson-config").json()
        assert first["config"] == second["config"]
        assert first["ready"] is True


class TestExtendedLessonConfiguration:
    def test_dates_method_template_and_per_indicator_resources_round_trip(self, http):
        scheme = http.scheme_factory()
        payload = {
            **FULL_CONFIG,
            "term": "Second Term",
            "term_start_date": "2027-01-05",
            "term_end_date": "2027-04-01",
            "lessons_per_week": 4,
            "generation_method": "zeli",
            "ai_mode": "OFF",
            "template_id": "",
            "indicator_resources": {
                "week1:0:B9.1.1.1.1": {
                    "references": ["Science Textbook p.10"],
                    "tlrs": ["Chart"],
                },
                "week1:1:B9.1.1.1.2": {
                    "references": ["Science Textbook p.14"],
                    "tlrs": ["Samples"],
                },
            },
        }
        resp = http.put(f"/api/generation/{scheme.id}/lesson-config", json=payload)
        assert resp.status_code == 200, resp.text

        body = http.get(f"/api/generation/{scheme.id}/lesson-config").json()["config"]
        assert body["term"] == "Second Term"
        assert body["term_start_date"] == "2027-01-05"
        assert body["term_end_date"] == "2027-04-01"
        assert body["lessons_per_week"] == 4
        assert body["generation_method"] == "zeli"
        assert body["indicator_resources"]["week1:0:B9.1.1.1.1"]["references"] == [
            "Science Textbook p.10"]
        assert body["indicator_resources"]["week1:1:B9.1.1.1.2"]["tlrs"] == ["Samples"]

    def test_explicit_teacher_name_and_deliberate_blank_are_persisted(self, http):
        scheme = http.scheme_factory()
        resp = http.put(
            f"/api/generation/{scheme.id}/lesson-config",
            json={**FULL_CONFIG, "teacher_name": "Saved Teacher"},
        )
        assert resp.status_code == 200
        assert resp.json()["config"]["teacher_name"] == "Saved Teacher"
        # Reopening returns the teacher's value, not the profile default.
        body = http.get(f"/api/generation/{scheme.id}/lesson-config").json()["config"]
        assert body["teacher_name"] == "Saved Teacher"

        # A deliberately cleared name stays blank (the UI tracks the intent).
        assert http.put(
            f"/api/generation/{scheme.id}/lesson-config",
            json={**FULL_CONFIG, "teacher_name": ""},
        ).status_code == 200
        body = http.get(f"/api/generation/{scheme.id}/lesson-config").json()["config"]
        assert body["teacher_name"] in ("", None)

    def test_clear_and_restore_name_are_visible_in_the_save_response(self, http):
        """The UI records cleared intent from the PUT response.

        A stale name there would make the next reopen prefill from the profile
        again, even though the server GET correctly returns a blank name.
        """
        scheme = http.scheme_factory()
        clear = http.put(
            f"/api/generation/{scheme.id}/lesson-config",
            json={**FULL_CONFIG, "teacher_name": ""},
        )
        assert clear.status_code == 200
        assert clear.json()["config"]["teacher_name"] in ("", None)
        assert clear.json()["config"]["teacher_name_cleared"] is True

        restore = http.put(
            f"/api/generation/{scheme.id}/lesson-config",
            json={**FULL_CONFIG, "teacher_name": "Restored Teacher"},
        )
        assert restore.status_code == 200
        assert restore.json()["config"]["teacher_name"] == "Restored Teacher"
        assert restore.json()["config"].get("teacher_name_cleared") is not True
        body = http.get(f"/api/generation/{scheme.id}/lesson-config").json()["config"]
        assert body["teacher_name"] == "Restored Teacher"

    def test_explicit_text_and_date_clears_are_authoritative(self, http):
        """Blank is a teacher edit, not a missing value to fall back from."""
        scheme = http.scheme_factory()
        saved = {
            **FULL_CONFIG,
            "school_name": "Kpogede Community School",
            "reference": "NaCCA p.19",
            "period": "3rd & 4th",
            "term": "First Term",
            "template_id": "tpl-wapef-maths-b4",
            "term_start_date": "2027-01-05",
            "term_end_date": "2027-04-01",
        }
        assert http.put(
            f"/api/generation/{scheme.id}/lesson-config", json=saved,
        ).status_code == 200

        cleared = {
            **FULL_CONFIG,
            "school_name": "",
            "reference": "",
            "period": "",
            "term": "",
            "template_id": "",
            "term_start_date": None,
            "term_end_date": None,
            "teaching_days": [],
        }
        response = http.put(
            f"/api/generation/{scheme.id}/lesson-config", json=cleared,
        )
        assert response.status_code == 200
        for field in ("school_name", "reference", "period", "term",
                      "template_id", "term_start_date", "term_end_date"):
            assert response.json()["config"].get(field) in ("", None), field
        body = http.get(f"/api/generation/{scheme.id}/lesson-config").json()["config"]
        for field in ("school_name", "reference", "period", "term",
                      "template_id", "term_start_date", "term_end_date"):
            assert body.get(field) in ("", None), field
        assert body["teaching_days"] == []

    def test_teacher_name_defaults_to_the_profile_when_not_saved(self, http):
        scheme = http.scheme_factory()
        payload = {k: v for k, v in FULL_CONFIG.items() if k != "teacher_name"}
        assert http.put(
            f"/api/generation/{scheme.id}/lesson-config", json=payload
        ).status_code == 200
        body = http.get(f"/api/generation/{scheme.id}/lesson-config").json()["config"]
        assert body["teacher_name"] == "Guided Teacher"

    def test_invalid_date_order_and_resource_key_are_rejected(self, http):
        scheme = http.scheme_factory()
        bad_dates = {
            **FULL_CONFIG,
            "term_start_date": "2027-04-01",
            "term_end_date": "2027-01-05",
        }
        assert http.put(
            f"/api/generation/{scheme.id}/lesson-config", json=bad_dates
        ).status_code == 422

        bad_key = {
            **FULL_CONFIG,
            "indicator_resources": {"position-0": {"references": ["x"], "tlrs": []}},
        }
        assert http.put(
            f"/api/generation/{scheme.id}/lesson-config", json=bad_key
        ).status_code == 422

    def test_per_lesson_core_competencies_round_trip_and_normalize(self, http):
        scheme = http.scheme_factory()
        payload = {
            **FULL_CONFIG,
            "competency_selections": {
                "week1:0:B9.1.1.1.1": [
                    "Critical Thinking and Problem Solving",
                    "CC",
                    "Not an approved competency",
                ],
                "week1:0:B9.1.1.1.2": ["Digital Literacy (DL)"],
            },
        }
        assert http.put(
            f"/api/generation/{scheme.id}/lesson-config", json=payload
        ).status_code == 200
        body = http.get(f"/api/generation/{scheme.id}/lesson-config").json()["config"]
        assert body["competency_selections"]["week1:0:B9.1.1.1.1"] == [
            "Critical Thinking and Problem Solving (CP)",
            "Communication and Collaboration (CC)",
        ]
        assert body["competency_selections"]["week1:0:B9.1.1.1.2"] == [
            "Digital Literacy (DL)",
        ]

        # A later setup-only save must not wipe the per-lesson selections.
        assert http.put(
            f"/api/generation/{scheme.id}/lesson-config",
            json={**FULL_CONFIG, "class_size": 41},
        ).status_code == 200
        body = http.get(f"/api/generation/{scheme.id}/lesson-config").json()["config"]
        assert body["competency_selections"]["week1:0:B9.1.1.1.1"] == [
            "Critical Thinking and Problem Solving (CP)",
            "Communication and Collaboration (CC)",
        ]

    def test_saving_without_indicator_resources_keeps_existing_ones(self, http):
        scheme = http.scheme_factory()
        resources = {
            "week1:0:B9.1.1.1.1": {
                "references": ["Science Textbook p.10"],
                "tlrs": ["Chart"],
            },
        }
        assert http.put(
            f"/api/generation/{scheme.id}/lesson-config",
            json={**FULL_CONFIG, "indicator_resources": resources},
        ).status_code == 200

        # A later save that only edits teaching setup must not wipe them.
        assert http.put(
            f"/api/generation/{scheme.id}/lesson-config",
            json={**FULL_CONFIG, "class_size": 41},
        ).status_code == 200

        body = http.get(f"/api/generation/{scheme.id}/lesson-config").json()["config"]
        assert body["class_size"] == 41
        assert body["indicator_resources"] == resources

    def test_full_snapshot_survives_setup_only_save(self, http):
        """A save that omits per-lesson maps keeps the saved snapshot.

        Resources, competencies, teacher keywords and WAPEF choices are
        teacher-owned. Only a field actually sent by the modal may change.
        """
        scheme = http.scheme_factory()
        key = "week1:0:B9.1.1.1.1"
        snapshot = {
            **FULL_CONFIG,
            "school_name": "Kpogede Community School",
            "teacher_name": "Deladem Amegayie",
            "class_size": 37,
            "term": "Second Term",
            "term_start_date": "2027-01-05",
            "term_end_date": "2027-04-01",
            "period": "3rd & 4th",
            "lessons_per_week": 4,
            "template_id": "tpl-wapef-maths-b4",
            "generation_method": "zeli",
            "indicator_resources": {
                key: {"references": ["NaCCA B4 p.12"], "tlrs": ["Beans", "sticks"]},
            },
            "competency_selections": {key: ["Critical Thinking and Problem Solving (CP)"]},
            "indicator_keywords": {key: ["bundle", "regroup", "place value"]},
            "indicator_wapef": {
                key: {
                    "through_lines": ["Order discoverer"],
                    "gods_story": "Creation",
                },
            },
        }
        assert http.put(
            f"/api/generation/{scheme.id}/lesson-config", json=snapshot,
        ).status_code == 200

        # A setup-only save omits the maps entirely: absent is not a clear.
        setup_only = {
            key: value for key, value in snapshot.items()
            if key not in {
                "indicator_resources", "competency_selections",
                "indicator_keywords", "indicator_wapef",
            }
        }
        setup_only["class_size"] = 38
        assert http.put(
            f"/api/generation/{scheme.id}/lesson-config", json=setup_only,
        ).status_code == 200

        body = http.get(f"/api/generation/{scheme.id}/lesson-config").json()["config"]
        assert body["class_size"] == 38
        assert body["school_name"] == "Kpogede Community School"
        assert body["teacher_name"] == "Deladem Amegayie"
        assert body["term"] == "Second Term"
        assert body["term_start_date"] == "2027-01-05"
        assert body["term_end_date"] == "2027-04-01"
        assert body["period"] == "3rd & 4th"
        assert body["lessons_per_week"] == 4
        assert body["template_id"] == "tpl-wapef-maths-b4"
        assert body["generation_method"] == "zeli"
        assert body["indicator_resources"] == snapshot["indicator_resources"]
        assert body["competency_selections"] == snapshot["competency_selections"]
        assert body["indicator_keywords"] == snapshot["indicator_keywords"]
        assert body["indicator_wapef"] == snapshot["indicator_wapef"]

    def test_explicit_empty_map_clears_saved_entries(self, http):
        """An empty map the teacher sent is authoritative, not a stale draft."""
        scheme = http.scheme_factory()
        key = "week1:0:B9.1.1.1.1"
        saved = {
            **FULL_CONFIG,
            "indicator_resources": {
                key: {"references": ["NaCCA p.1"], "tlrs": ["Beans"]},
            },
            "competency_selections": {
                key: ["Critical Thinking and Problem Solving (CP)"],
            },
            "indicator_keywords": {key: ["bundle"]},
            "indicator_wapef": {key: {"gods_story": "Creation"}},
        }
        assert http.put(
            f"/api/generation/{scheme.id}/lesson-config", json=saved,
        ).status_code == 200

        clear = {
            **FULL_CONFIG,
            "indicator_resources": {},
            "competency_selections": {},
            "indicator_keywords": {},
            "indicator_wapef": {},
        }
        assert http.put(
            f"/api/generation/{scheme.id}/lesson-config", json=clear,
        ).status_code == 200
        body = http.get(f"/api/generation/{scheme.id}/lesson-config").json()["config"]
        assert body["indicator_resources"] == {}
        assert body["competency_selections"] == {}
        assert body["indicator_keywords"] == {}
        assert body["indicator_wapef"] == {}


def test_saved_snapshot_is_authoritative_for_generation_config():
    """A stale client payload can never override the saved plan snapshot."""
    saved = {
        "school_name": "Kpogede Community School",
        "teacher_name": "Deladem Amegayie",
        "class_size": 37,
        "lesson_duration_minutes": 70,
        "period": "3rd & 4th",
        "periods_per_week": 4,
        "teaching_days": [1, 3],
        "term": "Second Term",
        "term_start_date": "2027-01-05",
        "term_end_date": "2027-04-01",
        "template_id": "tpl-wapef-maths-b4",
        "generation_method": "zeli",
        "indicator_resources": {"week1:0:B4.1.1.1.1": {"references": ["p.12"], "tlrs": []}},
        "competency_selections": {"week1:0:B4.1.1.1.1": ["Critical Thinking and Problem Solving (CP)"]},
        "indicator_keywords": {"week1:0:B4.1.1.1.1": ["bundle"]},
        "indicator_wapef": {"week1:0:B4.1.1.1.1": {"through_lines": ["Careful work"]}},
        "reference": "NaCCA B4",
    }
    scheme_db = type("Scheme", (), {"lesson_config": saved})()
    config = TermConfig(scheme_of_work_id="scheme-1", school_name="Stale School")

    _apply_saved_lesson_config(None, scheme_db, config, None)

    assert config.school_name == "Kpogede Community School"
    assert config.teacher_name == "Deladem Amegayie"
    assert config.class_size == 37
    assert config.lesson_duration_minutes == 70
    assert config.period == "3rd & 4th"
    assert config.lessons_per_week == 4
    assert config.teaching_days == [1, 3]
    assert config.term == "Second Term"
    assert config.term_start_date.isoformat() == "2027-01-05"
    assert config.term_end_date.isoformat() == "2027-04-01"
    assert config.template_id == "tpl-wapef-maths-b4"
    assert config.generation_method.value == "zeli"
    assert config.indicator_resources == saved["indicator_resources"]
    assert config.competency_selections == saved["competency_selections"]
    assert config.indicator_keywords == saved["indicator_keywords"]
    assert config.indicator_wapef == saved["indicator_wapef"]
    assert config.references == ["NaCCA B4"]

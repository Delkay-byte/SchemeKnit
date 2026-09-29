"""
PART 7 — the teacher's school must actually persist.

The real defect: ``PUT /api/auth/me`` declared ``full_name`` and ``school_name``
as bare function parameters. FastAPI binds those to QUERY parameters, so the
JSON body the app sends (``{"full_name": ..., "school_name": ...}``) was read
by nobody: the endpoint returned 200 and the Settings page kept showing the
typed school, while the database held an empty string. Every lesson generated
afterwards therefore carried no school — in the workspace, the DOCX and the PDF.

These tests drive the endpoint the way the app does (a JSON body) and assert
the STORED value, so the silent no-op cannot return.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), "..")))

from src.auth import create_user_token
from src.database import Base, get_db, User
from src.main import app
from tests.conftest import make_school, make_user


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    from src.security import rate_limiter
    rate_limiter.reset()
    yield
    rate_limiter.reset()


@pytest.fixture
def http(tmp_path):
    """TestClient over an in-memory SQLite, with the ACTIVE session shared."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    client = TestClient(app)
    yield client, db
    app.dependency_overrides.pop(get_db, None)
    db.close()
    engine.dispose()


def _independent_teacher(db, email="independent.teacher@example.test"):
    """An account with no school membership (the PART 7 independent teacher)."""
    teacher = make_user(db, role="teacher", email=email)
    teacher.school_name = ""
    teacher.school_id = None
    db.commit()
    return {"Authorization": f"Bearer {create_user_token(teacher)}"}


class TestProfileSchoolPersistence:
    def test_a_json_body_updates_the_school_on_the_profile(self, http):
        client, db = http
        headers = _independent_teacher(db)
        res = client.put("/api/auth/me", json={
            "full_name": "Independent Teacher",
            "school_name": "Achimota Basic School",
        }, headers=headers)
        assert res.status_code == 200, res.text
        assert res.json()["school_name"] == "Achimota Basic School"

        # The database holds it, not just the response echo.
        stored = db.query(User).filter(User.email == "independent.teacher@example.test").first()
        db.refresh(stored)
        assert stored.school_name == "Achimota Basic School"
        assert client.get("/api/auth/me", headers=headers).json()["school_name"] == (
            "Achimota Basic School")

    def test_the_school_survives_a_later_name_only_update(self, http):
        client, db = http
        headers = _independent_teacher(db, "teacher2@example.test")
        client.put("/api/auth/me", json={"school_name": "St Mary's JHS"}, headers=headers)
        client.put("/api/auth/me", json={"full_name": "New Name"}, headers=headers)
        me = client.get("/api/auth/me", headers=headers).json()
        assert me["full_name"] == "New Name"
        # A field the request does not mention is left exactly as stored.
        assert me["school_name"] == "St Mary's JHS"

    def test_the_query_parameter_form_still_works(self, http):
        client, db = http
        headers = _independent_teacher(db, "teacher3@example.test")
        res = client.put("/api/auth/me?school_name=Legacy%20Form%20School", headers=headers)
        assert res.status_code == 200, res.text
        assert res.json()["school_name"] == "Legacy Form School"

    def test_an_empty_value_clears_the_school(self, http):
        client, db = http
        headers = _independent_teacher(db, "teacher4@example.test")
        client.put("/api/auth/me", json={"school_name": "Some School"}, headers=headers)
        client.put("/api/auth/me", json={"school_name": ""}, headers=headers)
        assert client.get("/api/auth/me", headers=headers).json()["school_name"] == ""

    def test_the_school_is_bounded_in_length(self, http):
        client, db = http
        headers = _independent_teacher(db, "teacher5@example.test")
        client.put("/api/auth/me", json={"school_name": "S" * 500}, headers=headers)
        stored = client.get("/api/auth/me", headers=headers).json()["school_name"]
        assert len(stored) == 200

    def test_a_school_attached_teacher_keeps_the_school_records_name(self, http):
        """The permission model: membership owns the name, not free text."""
        client, db = http
        school = make_school(db, name="Membership School")
        teacher = make_user(db, role="teacher", email="attached@example.test",
                            school_id=school.id)
        teacher.school_name = "Membership School"
        db.commit()

        headers = {"Authorization": f"Bearer {create_user_token(teacher)}"}
        client.put("/api/auth/me", json={"school_name": "Somewhere Else"}, headers=headers)
        assert client.get("/api/auth/me", headers=headers).json()["school_name"] == (
            "Membership School")


class TestLessonCarriesTheSchool:
    """The stored school reaches the generated lesson (PART 7 / PART 27)."""

    def test_resolve_school_name_prefers_the_membership_then_the_profile(self, http):
        from src.routers.generation import _resolve_school_name

        _client, db = http
        school = make_school(db, name="Membership School")
        attached = make_user(db, role="teacher", email="attached2@example.test",
                             school_id=school.id)
        db.commit()
        assert _resolve_school_name(db, attached) == "Membership School"

        independent = make_user(db, role="teacher", email="indep2@example.test")
        independent.school_name = "Achimota Basic School"
        db.commit()
        assert _resolve_school_name(db, independent) == "Achimota Basic School"

        nameless = make_user(db, role="teacher", email="indep3@example.test")
        nameless.school_name = ""
        nameless.school_id = None
        db.commit()
        # No school stated anywhere: an empty header cell, never a placeholder.
        assert _resolve_school_name(db, nameless) in (None, "")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))

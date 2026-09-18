"""
Web acceptance through the real HTTP API (items 5-7, 15-17).

Everything here is a real round trip through the FastAPI ASGI app — real auth,
real multipart upload, real generation, real export bytes — not a router
function call. It exercises the path a browser takes:

  login -> upload real scheme -> review -> approve -> configure -> generate
  (AI OFF) -> open lesson -> edit -> save -> approved template -> export DOCX
  -> export ZIP -> open a ZIP member -> structural validation.

PDF is asserted separately: with no converter installed the backend must answer
the controlled 503, never a raw 500 and never a fake PDF body.

Skipped cleanly when the real uploaded scheme is absent.
"""

import io
import os
import sys
import zipfile
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.auth import create_access_token, hash_password  # noqa: E402
from src.database import Base, get_db, generate_id, User  # noqa: E402
from src.main import app  # noqa: E402
from tests.conftest import make_school, make_product_plan, make_license  # noqa: E402

SCHEME_FILENAME = "1d3813d1-8fce-47b1-ac81-2ab40c5a8bb8_BASIC 9 SCIENCE SCHEME OF LEARNING.docx"
SCHEME_PATH = Path(__file__).parent.parent / "uploads" / SCHEME_FILENAME
DOCX_MIME = ("application/vnd.openxmlformats-officedocument"
             ".wordprocessingml.document")

pytestmark = pytest.mark.skipif(
    not SCHEME_PATH.exists(), reason="real Basic 9 Science scheme not uploaded")


@pytest.fixture
def http(tmp_path, monkeypatch):
    """A TestClient whose app shares ONE in-memory SQLite connection.

    The default in-memory SQLite pool keeps a connection per thread, so a
    threadpool request would land on a fresh empty database. ``StaticPool``
    pins every thread to the same connection, which is what a real server's
    single on-disk database looks like to the app.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

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

    # A teacher in a licensed school (so the workflow endpoints admit them).
    school = make_school(db)
    plan = make_product_plan(db)
    make_license(db, school.id, plan.id, status="active")
    user = User(
        id=generate_id(), email="webacceptance@t.test", full_name="Web Teacher",
        hashed_password=hash_password("Strong1!Pass"), school_name=school.name,
        is_active=True, role="teacher", school_id=school.id,
    )
    db.add(user)
    db.commit()
    token = create_access_token({"sub": user.id, "role": user.role})
    client.headers.update({"Authorization": f"Bearer {token}"})
    yield client
    app.dependency_overrides.pop(get_db, None)
    db.close()
    engine.dispose()


def _upload_scheme(client):
    """Upload the real scheme via the HTTP API and return the scheme_id."""
    with open(SCHEME_PATH, "rb") as fh:
        res = client.post(
            "/api/documents/upload",
            files={"file": (SCHEME_PATH.name, fh.read(), DOCX_MIME)},
        )
    assert res.status_code == 200, res.text
    return res.json()["scheme_id"]


class TestTeacherWorkflowOverHttp:
    def test_full_workflow_and_approved_docx(self, http):
        scheme_id = _upload_scheme(http)

        # Review
        review = http.get(f"/api/curriculum/{scheme_id}/validate")
        assert review.status_code == 200
        assert review.json()["summary"]["subject"] == "Science"
        assert review.json()["summary"]["class_level"] == "Basic 9"

        # Approve
        approve = http.post(f"/api/curriculum/{scheme_id}/approve")
        assert approve.status_code == 200

        # Configure + generate, AI OFF, approved organizational template
        from src.models import AIMode
        config = {
            "scheme_of_work_id": scheme_id,
            "academic_year": "2026/2027", "term": "First Term",
            "class_level": "Basic 9", "subject": "Science",
            "class_size": 24, "lesson_duration_minutes": 60,
            "lessons_per_week": 2, "teaching_days": [0, 2],
            "term_start_date": "2026-09-11", "term_end_date": "2026-12-18",
            "holidays": [], "ai_mode": AIMode.OFF.value,
            "template_id": "tpl-approved-org-headteacher",
            "include_special_weeks": False,
            "school_name": "Acceptance School", "teacher_name": "Web Teacher",
        }
        gen = http.post(f"/api/generation/{scheme_id}/generate", json=config)
        assert gen.status_code == 200, gen.text
        job_id = gen.json()["job_id"]
        assert gen.json()["status"] == "completed"

        # Open the generated lessons
        lessons = http.get(f"/api/generation/{job_id}/lessons").json()
        assert lessons["total"] >= 1
        first = lessons["lesson_plans"][0]
        assert first["class_level"] == "Basic 9"
        assert first["subject"] == "Science"
        assert "Diversity of Matter" == first["strand"]

        # Edit and save (teacher edit path)
        edit = http.put(f"/api/generation/lessons/{first['id']}",
                        json={"introduction": "Edited starter by the teacher."})
        assert edit.status_code == 200, edit.text
        assert "Edited starter by the teacher." in edit.json()["introduction"]

        # Export DOCX with the approved template
        res = http.post(
            f"/api/generation/{job_id}/export/docx",
            params={"template_type": "GES-style",
                    "template_id": "tpl-approved-org-headteacher"})
        assert res.status_code == 200, res.text
        assert res.headers["content-type"] == DOCX_MIME
        assert res.headers["X-TeachFlow-Filename"].endswith(".docx")

        # Structural comparison against the approved SOURCE document
        from src.validators.docx_structure_compare import (
            golden_master_source_path, validate_generated,
        )
        out = Path("temp") / f"web_{job_id}.docx"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(res.content)
        report = validate_generated(
            out,
            expected_values=["Basic 9", "Diversity of Matter", "Materials",
                             "B9.1.1.1", "Edited starter by the teacher."],
            forbidden_values=["Forces & Energy", "B7.4.3.1",
                              "Responding to questions, brainstorming"],
            source_path=golden_master_source_path(),
        )
        assert report["pass"], [
            (g, c["name"], c["detail"])
            for g in ("structure", "content")
            for c in report[g]["checks"] if not c["pass"]]

    def test_zip_export_member_structurally_valid(self, http):
        scheme_id = _upload_scheme(http)
        http.post(f"/api/curriculum/{scheme_id}/approve")
        from src.models import AIMode
        config = {
            "scheme_of_work_id": scheme_id,
            "academic_year": "2026/2027", "term": "First Term",
            "class_level": "Basic 9", "subject": "Science",
            "class_size": 24, "lesson_duration_minutes": 60,
            "lessons_per_week": 2, "teaching_days": [0, 2],
            "term_start_date": "2026-09-11", "term_end_date": "2026-12-18",
            "holidays": [], "ai_mode": AIMode.OFF.value,
            "template_id": "tpl-approved-org-headteacher",
            "include_special_weeks": False,
        }
        job_id = http.post(f"/api/generation/{scheme_id}/generate",
                           json=config).json()["job_id"]

        res = http.post(
            f"/api/generation/{job_id}/export/zip",
            params={"template_type": "GES-style",
                    "template_id": "tpl-approved-org-headteacher"})
        assert res.status_code == 200, res.text
        assert res.headers["content-type"] == "application/zip"

        from src.validators.docx_structure_compare import (
            golden_master_source_path, validate_generated,
        )
        with zipfile.ZipFile(io.BytesIO(res.content)) as zf:
            members = [n for n in zf.namelist() if n.lower().endswith(".docx")]
            assert len(members) >= 1
            member_path = Path("temp") / f"webzip_{members[0]}"
            member_path.parent.mkdir(parents=True, exist_ok=True)
            member_path.write_bytes(zf.read(members[0]))

        report = validate_generated(
            member_path,
            expected_values=["Basic 9", "Diversity of Matter", "B9.1.1.1"],
            forbidden_values=["Forces & Energy", "B7.4.3.1"],
            source_path=golden_master_source_path(),
        )
        assert report["pass"], [
            (g, c["name"], c["detail"])
            for g in ("structure", "content")
            for c in report[g]["checks"] if not c["pass"]]


class TestPdfEndpointBehaviourOverHttp:
    def test_no_converter_is_a_controlled_503(self, http, monkeypatch):
        """Item 17: PDF generation backend is unavailable on this host, so the
        endpoint must answer the controlled 503 — never a raw 500 and never a
        body that is not a PDF."""
        from src.engines.pdf_export import PDFExportEngine
        monkeypatch.setattr(PDFExportEngine, "is_available", lambda: False)

        # A job is needed for the endpoint to reach the converter check.
        scheme_id = _upload_scheme(http)
        http.post(f"/api/curriculum/{scheme_id}/approve")
        from src.models import AIMode
        config = {
            "scheme_of_work_id": scheme_id,
            "academic_year": "2026/2027", "term": "First Term",
            "class_level": "Basic 9", "subject": "Science",
            "class_size": 24, "lesson_duration_minutes": 60,
            "lessons_per_week": 1, "teaching_days": [0],
            "term_start_date": "2026-09-11", "term_end_date": "2026-12-18",
            "holidays": [], "ai_mode": AIMode.OFF.value,
            "include_special_weeks": False,
        }
        job_id = http.post(f"/api/generation/{scheme_id}/generate",
                           json=config).json()["job_id"]

        res = http.post(f"/api/generation/{job_id}/export/pdf")
        assert res.status_code == 503
        assert "LibreOffice" in res.json()["detail"]

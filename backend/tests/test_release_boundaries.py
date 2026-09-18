"""
Release boundary tests: expiry edges, orphan cleanup, PDF-unavailable contract,
login failure audit-safety.
"""

import os
import sys
from datetime import date, timedelta, datetime

import pytest
from fastapi import HTTPException
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.conftest import make_user, make_school, make_product_plan, make_license, make_activation_code
from src.service import data_service
from src.database import SchemeDB, GenerationJobDB, generate_id
from src.routers.auth import login, LoginRequest, _usable_license
from src.engines.pdf_export import PDFExportEngine, PDF_CONVERTER_REQUIREMENT


class TestExpiryBoundaries:
    def test_license_expiring_today_usable(self, db):
        school = make_school(db)
        plan = make_product_plan(db)
        lic = make_license(db, school.id, plan.id)
        lic.expiry_date = date.today()
        db.commit()
        assert _usable_license(db, school.id) is not None

    def test_license_expired_yesterday_unusable(self, db):
        school = make_school(db)
        plan = make_product_plan(db)
        lic = make_license(db, school.id, plan.id)
        lic.expiry_date = date.today() - timedelta(days=1)
        db.commit()
        assert _usable_license(db, school.id) is None

    def test_activation_code_expiry_edge(self, db):
        from src.routers.auth import _validate_code_state
        school = make_school(db)
        plan = make_product_plan(db)
        lic = make_license(db, school.id, plan.id)
        code = make_activation_code(db, lic.id)
        code.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.commit()
        with pytest.raises(HTTPException) as e:
            _validate_code_state(db, code)
        assert e.value.status_code == 403


class TestOrphanCleanup:
    def test_delete_removes_storage_file(self, db, tmp_path):
        from tests.conftest import make_user
        u = make_user(db, role="teacher", email="orphan@t.test")
        f = tmp_path / "scheme_store.docx"
        f.write_bytes(b"fake-docx")
        scheme = SchemeDB(id=generate_id(), owner_id=u.id, filename="s.docx",
                          subject="Science", class_level="Basic 9",
                          storage_filename=str(f))
        db.add(scheme)
        db.commit()
        assert data_service.delete_scheme(db, scheme.id, u.id) is True
        assert not f.exists()

    def test_delete_keeps_shared_file(self, db, tmp_path):
        from tests.conftest import make_user
        u = make_user(db, role="teacher", email="orphan2@t.test")
        f = tmp_path / "shared.docx"
        f.write_bytes(b"fake-docx")
        s1 = SchemeDB(id=generate_id(), owner_id=u.id, filename="a.docx",
                      subject="Science", class_level="Basic 9",
                      storage_filename=str(f))
        s2 = SchemeDB(id=generate_id(), owner_id=u.id, filename="b.docx",
                      subject="Math", class_level="Basic 9",
                      storage_filename=str(f))
        db.add_all([s1, s2])
        db.commit()
        assert data_service.delete_scheme(db, s1.id, u.id) is True
        assert f.exists()

    def test_delete_blocked_with_children(self, db):
        from tests.conftest import make_user
        from fastapi import HTTPException
        from src.routers import documents as documents_router
        u = make_user(db, role="teacher", email="orphan4@t.test")
        scheme = SchemeDB(id=generate_id(), owner_id=u.id, filename="s.docx",
                          subject="Science", class_level="Basic 9")
        db.add(scheme)
        db.commit()
        job = GenerationJobDB(id=generate_id(), owner_id=u.id, scheme_id=scheme.id,
                              status="completed")
        db.add(job)
        db.commit()
        assert data_service.scheme_has_children(db, scheme.id, u.id) is True
        import asyncio
        with pytest.raises(HTTPException) as e:
            asyncio.run(documents_router.delete_scheme(scheme.id, u, db))
        assert e.value.status_code == 409
        # nothing deleted
        assert db.query(SchemeDB).filter(SchemeDB.id == scheme.id).first() is not None

    def test_blocked_delete_keeps_the_source_file(self, db, tmp_path):
        """A protected scheme must keep both its history and its upload."""
        from tests.conftest import make_user
        from fastapi import HTTPException
        from src.routers import documents as documents_router
        u = make_user(db, role="teacher", email="orphan5@t.test")
        f = tmp_path / "keep-me.docx"
        f.write_bytes(b"fake-docx")
        scheme = SchemeDB(id=generate_id(), owner_id=u.id, filename="s.docx",
                          subject="Science", class_level="Basic 9",
                          storage_filename=str(f))
        db.add(scheme)
        db.commit()
        job = GenerationJobDB(id=generate_id(), owner_id=u.id, scheme_id=scheme.id,
                              status="completed", completed_lessons=1)
        db.add(job)
        db.commit()
        import asyncio
        with pytest.raises(HTTPException) as e:
            asyncio.run(documents_router.delete_scheme(scheme.id, u, db))
        assert e.value.status_code == 409
        assert "preserved" in e.value.detail
        assert f.exists()

    def test_delete_missing_file_ok(self, db):
        from tests.conftest import make_user
        u = make_user(db, role="teacher", email="orphan3@t.test")
        scheme = SchemeDB(id=generate_id(), owner_id=u.id, filename="s.docx",
                          subject="Science", class_level="Basic 9",
                          storage_filename="/nonexistent/gone.docx")
        db.add(scheme)
        db.commit()
        assert data_service.delete_scheme(db, scheme.id, u.id) is True


class TestPdfContract:
    def test_unavailable_message_is_explicit(self):
        assert "LibreOffice" in PDF_CONVERTER_REQUIREMENT
        assert "500" not in PDF_CONVERTER_REQUIREMENT

    @pytest.mark.asyncio
    async def test_endpoint_503_when_no_converter(self, db):
        from tests.conftest import make_user
        from src.routers import generation as gen_router
        u = make_user(db, role="teacher", email="pdf@t.test")
        school = make_school(db)
        scheme = SchemeDB(id=generate_id(), owner_id=u.id, school_id=school.id,
                          filename="s.docx", subject="Science", class_level="Basic 9")
        db.add(scheme)
        db.commit()
        job = GenerationJobDB(id=generate_id(), owner_id=u.id, scheme_id=scheme.id,
                              status="completed", completed_lessons=1)
        db.add(job)
        db.flush()
        from src.database import LessonPlanDB
        db.add(LessonPlanDB(id=generate_id(), job_id=job.id, owner_id=u.id,
                            scheme_id=scheme.id, week_number=1, lesson_sequence=1,
                            class_level="Basic 9", subject="Science"))
        db.commit()
        with patch.object(PDFExportEngine, "is_available", return_value=False):
            with pytest.raises(HTTPException) as e:
                await gen_router.export_pdf(job.id, "GES-style", None, u, db)
        assert e.value.status_code == 503
        assert "LibreOffice" in e.value.detail


class TestLoginAuditSafety:
    @pytest.mark.asyncio
    async def test_failed_login_no_leak(self, db, caplog):
        from tests.conftest import make_user
        make_user(db, role="teacher", email="leak@t.test")
        with pytest.raises(HTTPException) as e:
            await login(LoginRequest(email="leak@t.test", password="WRONG-PW-123"), db)
        assert e.value.status_code == 401
        assert "WRONG-PW-123" not in e.value.detail

    @pytest.mark.asyncio
    async def test_unknown_email_same_message(self, db):
        with pytest.raises(HTTPException) as e:
            await login(LoginRequest(email="nobody@t.test", password="whatever123"), db)
        assert e.value.status_code == 401
        assert e.value.detail == "Invalid email or password"

"""
Scheme deletion acceptance (item 15).

Contract:
- EMPTY SCHEME: owner can delete; the source file is removed when no other
  scheme references it (orphan-safe cleanup).
- SCHEME WITH GENERATED CONTENT: hard delete is blocked with 409 and a clear
  message — generated lessons/history are never cascade-deleted.
- OTHER TEACHER'S SCHEME: 403 (exists but not yours) / 404 (does not exist),
  per the diagnostic authorization model.
"""

import asyncio
import os
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.routers.documents import delete_scheme, _resolve_scheme_or_raise  # noqa: E402
from src.service import data_service  # noqa: E402


def _make_scheme(db, owner_id, storage_filename=None):
    from src.database import SchemeDB, generate_id

    scheme = SchemeDB(
        id=generate_id(), owner_id=owner_id, filename="BASIC 9 SCIENCE SCHEME OF LEARNING.docx",
        storage_filename=storage_filename, subject="Science", class_level="Basic 9")
    db.add(scheme)
    db.commit()
    return scheme


def _make_job_with_lessons(db, owner_id, scheme_id):
    from src.database import GenerationJobDB, LessonPlanDB, generate_id

    job = GenerationJobDB(id=generate_id(), owner_id=owner_id, scheme_id=scheme_id,
                          status="completed", completed_lessons=1)
    db.add(job)
    db.flush()
    lp = LessonPlanDB(id=generate_id(), job_id=job.id, owner_id=owner_id,
                      scheme_id=scheme_id, week_number=1, lesson_sequence=1,
                      class_level="Basic 9", subject="Science",
                      strand="Diversity of Matter", assessment="Real generated content.")
    db.add(lp)
    db.commit()
    return job, lp


class TestEmptySchemeDelete:
    def test_owner_can_delete_empty_scheme(self, db):
        from tests.conftest import make_user

        owner = make_user(db, role="teacher", email="del-owner@t.test")
        scheme = _make_scheme(db, owner.id)
        assert data_service.scheme_has_children(db, scheme.id, owner.id) is False

        result = asyncio.run(delete_scheme(scheme.id, owner, db))
        assert result == {"message": "Scheme deleted"}
        assert data_service.scheme_exists(db, scheme.id) is False

    def test_source_file_removed_on_delete(self, db, tmp_path):
        from tests.conftest import make_user

        owner = make_user(db, role="teacher", email="del-file@t.test")
        storage = tmp_path / "scheme_source.docx"
        storage.write_bytes(b"PK\x03\x04 real docx bytes")
        scheme = _make_scheme(db, owner.id, storage_filename=str(storage))

        asyncio.run(delete_scheme(scheme.id, owner, db))
        assert not storage.exists()  # file cleaned up with the row

    def test_file_kept_when_another_scheme_shares_it(self, db, tmp_path):
        from tests.conftest import make_user

        owner = make_user(db, role="teacher", email="del-share@t.test")
        storage = tmp_path / "shared_source.docx"
        storage.write_bytes(b"PK\x03\x04 shared bytes")
        _make_scheme(db, owner.id, storage_filename=str(storage))
        scheme2 = _make_scheme(db, owner.id, storage_filename=str(storage))

        asyncio.run(delete_scheme(scheme2.id, owner, db))
        assert storage.exists()  # still referenced by the surviving scheme


class TestGeneratedContentProtection:
    def test_delete_blocked_with_409_and_clear_message(self, db):
        from tests.conftest import make_user

        owner = make_user(db, role="teacher", email="del-gen@t.test")
        scheme = _make_scheme(db, owner.id)
        _make_job_with_lessons(db, owner.id, scheme.id)

        with pytest.raises(HTTPException) as e:
            asyncio.run(delete_scheme(scheme.id, owner, db))
        assert e.value.status_code == 409
        assert "generated lesson plans" in e.value.detail
        assert "preserved" in e.value.detail

    def test_generated_lessons_survive_a_blocked_delete_attempt(self, db):
        from src.database import LessonPlanDB

        from tests.conftest import make_user

        owner = make_user(db, role="teacher", email="del-keep@t.test")
        scheme = _make_scheme(db, owner.id)
        _job, lp = _make_job_with_lessons(db, owner.id, scheme.id)

        with pytest.raises(HTTPException):
            asyncio.run(delete_scheme(scheme.id, owner, db))

        still_there = db.query(LessonPlanDB).filter(LessonPlanDB.id == lp.id).first()
        assert still_there is not None
        assert still_there.strand == "Diversity of Matter"
        # And the scheme row itself is untouched:
        assert data_service.scheme_exists(db, scheme.id) is True


class TestSchemeDeleteAuthorization:
    def test_other_teacher_gets_403(self, db):
        from tests.conftest import make_user

        owner = make_user(db, role="teacher", email="del-own@t.test")
        other = make_user(db, role="teacher", email="del-other@t.test")
        scheme = _make_scheme(db, owner.id)

        with pytest.raises(HTTPException) as e:
            asyncio.run(delete_scheme(scheme.id, other, db))
        assert e.value.status_code == 403

    def test_unknown_scheme_gets_404(self, db):
        from tests.conftest import make_user

        user = make_user(db, role="teacher", email="del-404@t.test")
        with pytest.raises(HTTPException) as e:
            asyncio.run(delete_scheme("no-such-scheme-id", user, db))
        assert e.value.status_code == 404

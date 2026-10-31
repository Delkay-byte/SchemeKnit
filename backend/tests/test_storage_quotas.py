"""Storage quota: atomic accounting, durable originals, reconciliation."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from src import storage_quota  # noqa: E402
from src.config import get_settings  # noqa: E402
from src.database import (  # noqa: E402
    Base, SchemeDB, StorageCounterDB, StorageLedgerDB, get_db, generate_id,
)
from src.routers import documents as documents_router  # noqa: E402
from src.auth import get_current_user, require_teacher_workflow  # noqa: E402
from tests.conftest import make_user  # noqa: E402

SCHEME = BACKEND / "uploads" / (
    "1d3813d1-8fce-47b1-ac81-2ab40c5a8bb8_BASIC 9 SCIENCE SCHEME OF LEARNING.docx")
DOCX_MIME = ("application/vnd.openxmlformats-officedocument"
             ".wordprocessingml.document")
MIB = 1024 * 1024


def _app(db, user):
    app = FastAPI()
    app.include_router(documents_router.router, prefix="/api/documents")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_teacher_workflow] = lambda: user
    return app


@pytest.fixture(autouse=True)
def _storage_env(tmp_path, monkeypatch):
    monkeypatch.setenv("TEACHFLOW_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("STORAGE_USER_QUOTA_BYTES", str(500 * MIB))
    monkeypatch.setenv("STORAGE_GLOBAL_QUOTA_BYTES", str(8 * 1024 * MIB))
    monkeypatch.setenv("STORAGE_MAX_FILE_BYTES", str(50 * MIB))
    get_settings.cache_clear()
    import src.storage as storage_module
    storage_module._storage = None
    yield
    storage_module._storage = None
    get_settings.cache_clear()


def _upload(client, data=None, name="scheme.docx"):
    if data is None:
        data = SCHEME.read_bytes()
    return client.post(
        "/api/documents/upload",
        files={"file": (name, data, DOCX_MIME)},
    )


# ── Core ledger behaviour ──────────────────────────────────────────────────

def test_reservation_is_committed_and_counted_once(db):
    r = storage_quota.reserve(
        db, "teacher-1", object_key="production/uploads/t/a.docx",
        size_bytes=1234, file_type=".docx")
    assert storage_quota.commit(db, r) is True
    assert storage_quota.commit(db, r) is True  # idempotent
    usage = storage_quota.usage(db, "teacher-1")
    assert usage["used_bytes"] == 1234
    assert usage["remaining_bytes"] == usage["quota_bytes"] - 1234
    assert db.query(StorageLedgerDB).one().state == "committed"


def test_failed_reservation_releases_quota(db):
    r = storage_quota.reserve(
        db, "teacher-1", object_key="production/uploads/t/a.docx",
        size_bytes=999)
    assert storage_quota.release(db, r) is True
    assert storage_quota.release(db, r) is False
    assert storage_quota.usage(db, "teacher-1")["total_bytes"] == 0


def test_same_idempotency_key_reserves_once(db):
    first = storage_quota.reserve(
        db, "teacher-1", object_key="production/uploads/t/a.docx",
        size_bytes=500, idempotency_key="upload-1")
    second = storage_quota.reserve(
        db, "teacher-1", object_key="production/uploads/t/a.docx",
        size_bytes=500, idempotency_key="upload-1")
    assert first.id == second.id
    row = db.query(StorageCounterDB).filter(
        StorageCounterDB.scope == "user").one()
    assert row.reserved_bytes == 500


def test_deletion_releases_exactly_once(db):
    r = storage_quota.reserve(
        db, "teacher-1", object_key="production/uploads/t/a.docx",
        size_bytes=700)
    storage_quota.commit(db, r)
    assert storage_quota.release_object(db, r.object_key) is True
    assert storage_quota.release_object(db, r.object_key) is False
    assert storage_quota.usage(db, "teacher-1")["total_bytes"] == 0


def test_user_quota_is_atomic_across_workers(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'quota.db'}",
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    def attempt(i):
        session = Session()
        try:
            storage_quota.reserve(
                session, "teacher-1",
                object_key=f"production/uploads/t/{i}.docx",
                size_bytes=300 * 1024,
                idempotency_key=f"upload-{i}",
            )
            return True
        except storage_quota.StorageQuotaError:
            return False
        finally:
            session.close()

    # 500 MiB quota; each reservation 300 KiB. Only a bounded number fit.
    results = [attempt(i) for i in range(10)]
    assert all(results)
    usage_session = Session()
    usage = storage_quota.usage(usage_session, "teacher-1")
    usage_session.close()
    assert usage["total_bytes"] <= usage["quota_bytes"]


def test_global_quota_blocks_a_second_teacher(db, monkeypatch):
    monkeypatch.setenv("STORAGE_GLOBAL_QUOTA_BYTES", str(2 * MIB))
    get_settings.cache_clear()
    storage_quota.reserve(
        db, "teacher-1", object_key="production/uploads/t/a.docx",
        size_bytes=MIB + MIB // 2)
    with pytest.raises(storage_quota.StorageQuotaError) as exc:
        storage_quota.reserve(
            db, "teacher-2", object_key="production/uploads/t/b.docx",
            size_bytes=MIB)
    assert exc.value.code == "storage_global_quota_exceeded"


def test_reconcile_reports_orphans_without_deleting_valid_objects(db):
    class FakeStorage:
        def __init__(self):
            self.deleted = []
            self.objects = {
                "production/uploads/a/used.docx": (10, __import__(
                    "datetime").datetime.utcnow()),
                "production/uploads/a/orphan.docx": (20, __import__(
                    "datetime").datetime.utcnow()),
            }

        def list_objects(self, prefix=""):
            return [(k, s, m) for k, (s, m) in self.objects.items()]

        def delete(self, key):
            self.deleted.append(key)

    user = make_user(db)
    scheme = SchemeDB(
        id=generate_id(), owner_id=user.id, filename="used.docx",
        subject="Science", class_level="Basic 9",
        storage_filename="production/uploads/a/used.docx",
    )
    db.add(scheme)
    db.commit()
    fake = FakeStorage()
    report = storage_quota.reconcile(
        db, fake, dry_run=True, delete_orphans=False)
    assert report["orphan_candidates"] == ["production/uploads/a/orphan.docx"]
    assert fake.deleted == []


# ── HTTP upload flow ───────────────────────────────────────────────────────

@pytest.mark.skipif(not SCHEME.exists(), reason="real scheme fixture missing")
def test_upload_counts_actual_bytes_and_exposes_usage(db, tmp_path):
    user = make_user(db)
    with TestClient(_app(db, user)) as client:
        data = SCHEME.read_bytes()
        res = _upload(client, data)
        assert res.status_code == 200, res.text
        usage = client.get("/api/documents/storage").json()
    assert usage["used_bytes"] == len(data)
    assert usage["quota_bytes"] == 500 * MIB
    assert usage["max_file_bytes"] == 50 * MIB
    assert usage["used_human"].endswith(("KiB", "MiB", "B"))


@pytest.mark.skipif(not SCHEME.exists(), reason="real scheme fixture missing")
def test_per_file_limit_rejects_before_storing(db, monkeypatch):
    monkeypatch.setenv("STORAGE_MAX_FILE_BYTES", str(MIB))
    get_settings.cache_clear()
    user = make_user(db)
    oversized_pdf = b"%PDF-1.4\n" + (b"x" * (MIB + 16))
    with TestClient(_app(db, user)) as client:
        res = client.post(
            "/api/documents/upload",
            files={"file": ("big.pdf", oversized_pdf, "application/pdf")},
        )
    assert res.status_code == 413
    assert db.query(StorageLedgerDB).count() == 0


@pytest.mark.skipif(not SCHEME.exists(), reason="real scheme fixture missing")
def test_user_quota_exhaustion_rejects_without_partial_document(db):
    user = make_user(db)
    db.add(StorageCounterDB(
        id=generate_id(), scope="user", key=user.id,
        committed_bytes=500 * MIB - 100, reserved_bytes=0))
    db.commit()
    with TestClient(_app(db, user)) as client:
        res = _upload(client)
    assert res.status_code == 507
    assert res.json()["detail"]["code"] == "storage_user_quota_exceeded"
    assert db.query(SchemeDB).count() == 0


@pytest.mark.skipif(not SCHEME.exists(), reason="real scheme fixture missing")
def test_global_quota_exhaustion_rejects(db):
    user = make_user(db)
    db.add(StorageCounterDB(
        id=generate_id(), scope="global", key="production",
        committed_bytes=8 * 1024 * MIB - 100, reserved_bytes=0))
    db.commit()
    with TestClient(_app(db, user)) as client:
        res = _upload(client)
    assert res.status_code == 507
    assert res.json()["detail"]["code"] == "storage_global_quota_exceeded"
    assert db.query(SchemeDB).count() == 0


def test_invalid_file_creates_no_object_or_reservation(db):
    user = make_user(db)
    with TestClient(_app(db, user)) as client:
        res = client.post(
            "/api/documents/upload",
            files={"file": ("bad.pdf", b"not a pdf", "application/pdf")},
        )
    assert res.status_code == 400
    assert db.query(StorageLedgerDB).count() == 0


@pytest.mark.skipif(not SCHEME.exists(), reason="real scheme fixture missing")
def test_storage_failure_releases_reservation(db, monkeypatch):
    user = make_user(db)

    class BrokenStorage:
        def save_file(self, path, key):
            raise TimeoutError("R2 timeout")

        def exists(self, key):
            return False

        def delete(self, key):
            pass

    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.setattr(
        documents_router, "get_storage", lambda: BrokenStorage())
    with TestClient(_app(db, user)) as client:
        res = _upload(client)
    assert res.status_code == 422
    assert db.query(SchemeDB).count() == 0
    assert storage_quota.usage(db, user.id)["total_bytes"] == 0
    assert db.query(StorageLedgerDB).one().state == "released"


@pytest.mark.skipif(not SCHEME.exists(), reason="real scheme fixture missing")
def test_original_survives_a_simulated_restart(db, tmp_path):
    user = make_user(db)
    with TestClient(_app(db, user)) as client:
        res = _upload(client)
        scheme_id = res.json()["scheme_id"]
    # Drop all identity/state and read the row again in a new session.
    db.expire_all()
    scheme = db.query(SchemeDB).filter(SchemeDB.id == scheme_id).one()
    path, temporary = documents_router._materialize_upload(scheme)
    assert path is not None and path.exists()
    assert path.read_bytes()[:2] == b"PK"
    if temporary:
        Path(temporary).unlink(missing_ok=True)


@pytest.mark.skipif(not SCHEME.exists(), reason="real scheme fixture missing")
def test_other_teacher_cannot_delete_or_read_the_file(db):
    owner = make_user(db)
    other = make_user(db)
    with TestClient(_app(db, owner)) as client:
        scheme_id = _upload(client).json()["scheme_id"]
    with TestClient(_app(db, other)) as client:
        assert client.get(f"/api/documents/{scheme_id}").status_code in (403, 404)
        assert client.delete(f"/api/documents/{scheme_id}").status_code in (403, 404)
    assert storage_quota.usage(db, owner.id)["used_bytes"] > 0


@pytest.mark.skipif(not SCHEME.exists(), reason="real scheme fixture missing")
def test_delete_releases_teacher_quota(db):
    user = make_user(db)
    with TestClient(_app(db, user)) as client:
        scheme_id = _upload(client).json()["scheme_id"]
        assert client.delete(f"/api/documents/{scheme_id}").status_code == 200
        usage = client.get("/api/documents/storage").json()
    assert usage["used_bytes"] == 0

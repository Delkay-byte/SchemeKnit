"""Durable upload storage adapter tests (S3/R2-compatible via LocalStorage)."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from src.database import SchemeDB, generate_id
from src.routers import documents
from src.service import data_service
from src.storage import LocalStorage
from tests.conftest import make_user


def test_materialize_upload_downloads_private_key(tmp_path, monkeypatch):
    storage = LocalStorage(tmp_path / "objects")
    key = "production/uploads/user-1/opaque.docx"
    storage.save_bytes(key, b"PK\x03\x04test")
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.setattr(documents, "get_storage", lambda: storage)
    path, temp = documents._materialize_upload(
        SimpleNamespace(storage_filename=key))
    try:
        assert path is not None and temp == path
        assert path.read_bytes() == b"PK\x03\x04test"
    finally:
        if temp:
            temp.unlink(missing_ok=True)


def test_materialize_upload_missing_object_returns_none(tmp_path, monkeypatch):
    storage = LocalStorage(tmp_path / "objects")
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.setattr(documents, "get_storage", lambda: storage)
    path, temp = documents._materialize_upload(
        SimpleNamespace(storage_filename="production/uploads/missing.docx"))
    assert path is None and temp is None


def test_delete_scheme_removes_durable_object(db, tmp_path, monkeypatch):
    storage = LocalStorage(tmp_path / "objects")
    key = "production/uploads/user-1/delete.docx"
    storage.save_bytes(key, b"data")
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.setattr("src.storage._storage", storage)
    monkeypatch.setattr(
        "src.service.get_settings",
        lambda: SimpleNamespace(STORAGE_BACKEND="s3"),
    )

    user = make_user(db)
    scheme = SchemeDB(
        id=generate_id(), owner_id=user.id, filename="s.docx",
        subject="Science", class_level="Basic 9", storage_filename=key,
    )
    db.add(scheme)
    db.commit()

    assert data_service.delete_scheme(db, scheme.id, user.id) is True
    assert storage.exists(key) is False


def test_local_paths_still_work(tmp_path):
    local = tmp_path / "local.docx"
    local.write_bytes(b"PK\x03\x04local")
    path, temp = documents._materialize_upload(
        SimpleNamespace(storage_filename=str(local)))
    assert path == local
    assert temp is None

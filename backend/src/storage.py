"""
SchemeKnit Storage Abstraction
==============================

Provides a single, environment-driven interface for all user-file operations
(uploads, exports, temp files).  Production can switch from local disk to
any S3-compatible object store (AWS S3, MinIO, Cloudflare R2, Backblaze B2,
DigitalOcean Spaces, …) by changing environment variables — no code changes.

Configuration (environment variables)
-------------------------------------
    STORAGE_BACKEND=local          # or "s3"

    # Only used when STORAGE_BACKEND=s3
    S3_ENDPOINT=                   # e.g. https://s3.us-east-003.backblazeb2.com
    S3_REGION=                     # e.g. us-east-003
    S3_BUCKET=                     # bucket name
    S3_ACCESS_KEY=                 # access key id
    S3_SECRET_KEY=                 # secret access key

Using the storage layer
-----------------------
    from .storage import storage

    # Write
    storage.save_bytes("exports/userid/jobid/lesson_plans.docx", data)
    storage.save_file(local_temp_path, "exports/userid/jobid/lesson_plans.docx")

    # Read
    data = storage.get_bytes(key)
    storage.download_to_file(key, local_temp_path)

    # Delete / check
    storage.delete(key)
    storage.exists(key)

    # Serve to the client
    url = storage.get_url(key)          # signed URL (S3) or /files/ path (local)
    streaming_response = storage.get_response(key, filename=...)

Design rules
------------
* Never hard-code a vendor in business logic — everything goes through the
  StorageBackend protocol.
* The local backend is the default and preserves existing behaviour exactly.
* The S3 backend uses boto3 (already an optional dependency).
* Secrets are never logged.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

from fastapi.responses import FileResponse, Response

from .logging_config import get_logger

logger = get_logger()


# ── Interface ────────────────────────────────────────────────────────────

@runtime_checkable
class StorageBackend(Protocol):
    """Vendor-neutral interface for user-file storage."""

    def save_bytes(self, key: str, data: bytes) -> str:
        """Write *data* to *key*. Returns the storage key."""
        ...

    def save_file(self, local_path: str | Path, key: str) -> str:
        """Upload a local file to *key*. Returns the storage key."""
        ...

    def get_bytes(self, key: str) -> bytes:
        """Read *key* and return its bytes."""
        ...

    def download_to_file(self, key: str, local_path: str | Path) -> Path:
        """Download *key* to a local file (needed by python-docx etc.)."""
        ...

    def delete(self, key: str) -> None:
        """Delete *key* if it exists."""
        ...

    def exists(self, key: str) -> bool:
        """Return True if *key* exists."""
        ...

    def get_url(self, key: str, expires: int = 3600) -> str:
        """Return a URL the client can use to fetch the file.

        Local backend returns a relative ``/files/...`` path served by the
        ``StaticFiles`` mount.  S3 returns a time-limited presigned URL.
        """
        ...

    def get_response(self, key: str, filename: str = "",
                     media_type: str = "application/octet-stream") -> Response:
        """Return a FastAPI response that streams the file to the client."""
        ...


# ── Local filesystem backend ─────────────────────────────────────────────

class LocalStorage:
    """Stores files on the local filesystem (development / single-server)."""

    def __init__(self, root: str | Path = "uploads"):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _full(self, key: str) -> Path:
        # Prevent path traversal: key must stay under root
        full = (self.root / key).resolve()
        if not str(full).startswith(str(self.root)):
            raise ValueError(f"key escapes storage root: {key}")
        return full

    def save_bytes(self, key: str, data: bytes) -> str:
        full = self._full(key)
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(data)
        return key

    def save_file(self, local_path: str | Path, key: str) -> str:
        src = Path(local_path)
        full = self._full(key)
        full.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(full))
        return key

    def get_bytes(self, key: str) -> bytes:
        return self._full(key).read_bytes()

    def download_to_file(self, key: str, local_path: str | Path) -> Path:
        dest = Path(local_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(self._full(key)), str(dest))
        return dest

    def delete(self, key: str) -> None:
        full = self._full(key)
        if full.exists():
            full.unlink()

    def exists(self, key: str) -> bool:
        return self._full(key).exists()

    def get_url(self, key: str, expires: int = 3600) -> str:
        # Local files are served by the StaticFiles mount on /files/
        return f"/files/{key}"

    def get_response(self, key: str, filename: str = "",
                     media_type: str = "application/octet-stream") -> Response:
        full = self._full(key)
        return FileResponse(
            str(full),
            media_type=media_type,
            headers={"X-TeachFlow-Filename": filename} if filename else None,
        )


# ── S3-compatible object storage backend ────────────────────────────────

class S3Storage:
    """Any S3-compatible object store (AWS S3, MinIO, R2, B2, DO Spaces…).

    Uses boto3, which is an optional dependency — only import it when this
    backend is actually selected.
    """

    def __init__(
        self,
        endpoint: str = "",
        region: str = "",
        bucket: str = "",
        access_key: str = "",
        secret_key: str = "",
    ):
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise RuntimeError(
                "boto3 is required for STORAGE_BACKEND=s3. "
                "Install it with: pip install boto3"
            ) from exc

        self.bucket = bucket
        kwargs = dict(
            service_name="s3",
            region_name=region or None,
            aws_access_key_id=access_key or None,
            aws_secret_access_key=secret_key or None,
            config=Config(signature_version="s3v4"),
        )
        if endpoint:
            kwargs["endpoint_url"] = endpoint
        self.client = boto3.client(**kwargs)

    def save_bytes(self, key: str, data: bytes) -> str:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data)
        return key

    def save_file(self, local_path: str | Path, key: str) -> str:
        self.client.upload_file(str(local_path), self.bucket, key)
        return key

    def get_bytes(self, key: str) -> bytes:
        resp = self.client.get_object(Bucket=self.bucket, Key=key)
        return resp["Body"].read()

    def download_to_file(self, key: str, local_path: str | Path) -> Path:
        dest = Path(local_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        self.client.download_file(self.bucket, key, str(dest))
        return dest

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def get_url(self, key: str, expires: int = 3600) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires,
        )

    def get_response(self, key: str, filename: str = "",
                     media_type: str = "application/octet-stream") -> Response:
        body = self.get_bytes(key)
        headers = {"X-TeachFlow-Filename": filename} if filename else None
        return Response(content=body, media_type=media_type, headers=headers)


# ── Factory ──────────────────────────────────────────────────────────────

_storage: Optional[StorageBackend] = None


def _create_storage() -> StorageBackend:
    """Build the storage backend from environment variables."""
    backend = os.environ.get("STORAGE_BACKEND", "local").lower().strip()

    if backend == "s3":
        bucket = os.environ.get("S3_BUCKET", "")
        if not bucket:
            raise RuntimeError(
                "STORAGE_BACKEND=s3 requires S3_BUCKET. "
                "Set S3_ENDPOINT, S3_REGION, S3_BUCKET, S3_ACCESS_KEY, "
                "S3_SECRET_KEY in the environment."
            )
        logger.info("storage_backend_s3", bucket=bucket)
        return S3Storage(
            endpoint=os.environ.get("S3_ENDPOINT", ""),
            region=os.environ.get("S3_REGION", ""),
            bucket=bucket,
            access_key=os.environ.get("S3_ACCESS_KEY", ""),
            secret_key=os.environ.get("S3_SECRET_KEY", ""),
        )

    # Default: local filesystem
    root = os.environ.get(
        "TEACHFLOW_DATA_DIR",
        os.path.expanduser("~/teachflow_data"),
    )
    logger.info("storage_backend_local", root=root)
    return LocalStorage(root=root)


def get_storage() -> StorageBackend:
    """Return the process-wide storage backend (lazy singleton).

    Business code should call this function rather than caching the result
    at module level, so monkeypatched environment variables work in tests.
    """
    global _storage
    if _storage is None:
        _storage = _create_storage()
    return _storage

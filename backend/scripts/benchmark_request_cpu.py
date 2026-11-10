"""Measure in-process CPU per representative SchemeKnit request.

`time.process_time()` counts CPU actually executed by this process: it excludes
database and network waiting, which is the closest local proxy for Cloudflare's
"active CPU" accounting. It is NOT the Cloudflare meter: Workers execute Python
through Pyodide/WASM and enforce 10 ms per request, so a deployed measurement is
still required. This script gives the server-side floor.

Run from ``backend/``:
    python scripts/benchmark_request_cpu.py
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
import time
import traceback
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="schemeknit-bench-"))
os.environ["TEACHFLOW_DATA_DIR"] = str(TMP)
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("PAYSTACK_ENABLED", "false")
os.environ.setdefault("RATE_LIMIT_BACKEND", "memory")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from src.auth import create_session_record, create_user_token  # noqa: E402
from src.database import Base, get_db, generate_id  # noqa: E402
from src.main import app  # noqa: E402
from tests.conftest import make_user  # noqa: E402
from tests.test_export_download import (  # noqa: E402
    _grant_pro_entitlement, make_job_with_lessons)

SCHEME = (ROOT / "uploads" /
          "1d3813d1-8fce-47b1-ac81-2ab40c5a8bb8_BASIC 9 SCIENCE SCHEME OF LEARNING.docx")


def build_client():
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
    return client, db


def measure(client: TestClient, label: str, method: str, url: str, *,
            json_body=None, data=None, files=None, headers=None,
            repeats: int = 3, batch: int = 10) -> dict:
    """Batch requests so Windows' ~15.6 ms process-time tick cannot hide them.

    ``process_time`` on Windows advances in scheduler ticks, so a single fast
    request can read as 0 or 15.6 ms. Each sample is therefore the CPU used by a
    batch of requests divided by the batch size.
    """
    # Warm-up: imports, template caches, SQL compilation.
    for _ in range(min(batch, 3)):
        client.request(method, url, json=json_body, data=data,
                       files=files, headers=headers)

    cpu_samples = []
    wall_samples = []
    status = None
    per_request_wall = []
    for _ in range(repeats):
        cpu0 = time.process_time()
        wall0 = time.perf_counter()
        for _ in range(batch):
            tick = time.perf_counter()
            response = client.request(method, url, json=json_body, data=data,
                                      files=files, headers=headers)
            per_request_wall.append((time.perf_counter() - tick) * 1000)
            status = response.status_code
        total_cpu = (time.process_time() - cpu0) * 1000
        total_wall = (time.perf_counter() - wall0) * 1000
        cpu_samples.append(total_cpu / batch)
        wall_samples.append(total_wall / batch)

    ordered = sorted(cpu_samples)
    return {
        "route": f"{method} {url.split('?')[0]}",
        "label": label,
        "status": status,
        "batch_size": batch,
        "samples_cpu_ms": [round(x, 2) for x in cpu_samples],
        "median_cpu_ms": round(statistics.median(cpu_samples), 3),
        "p95_cpu_ms": round(ordered[min(len(ordered) - 1,
                                        int(len(ordered) * 0.95))], 3),
        "median_wall_ms": round(statistics.median(wall_samples), 3),
        "requests_measured": len(per_request_wall),
        "over_10ms_wall": sum(1 for x in per_request_wall if x > 10),
    }


def main() -> None:
    client, db = build_client()
    user = make_user(db, email="bench@example.com")
    _grant_pro_entitlement(db, user)
    _scheme, job = make_job_with_lessons(db, user, lessons=10)

    # Mint the token directly: the measured login request below still pays the
    # real bcrypt cost, but authenticated fixtures must not depend on the
    # rate-limiter's first-request behaviour.
    import secrets
    jti = secrets.token_hex(16)
    token = create_user_token(user, jti=jti)
    create_session_record(db, user.id, jti)
    headers = {"Authorization": f"Bearer {token}"}
    auth_mode = 200

    results = []
    results.append(measure(client, "health", "GET", "/api/health"))
    results.append(measure(client, "login + bcrypt", "POST", "/api/auth/login",
                           json_body={"email": "bench@example.com",
                                      "password": "testpass123",
                                      "entry": "teacher"}))

    if auth_mode == 200:
        results.append(measure(client, "list schemes", "GET",
                               "/api/documents/", headers=headers))
        results.append(measure(client, "list 10 lessons (large JSON)", "GET",
                               f"/api/generation/{job.id}/lessons",
                               headers=headers))
        results.append(measure(client, "coverage", "GET",
                               f"/api/generation/{job.id}/coverage",
                               headers=headers))
        results.append(measure(client, "export render model (new)", "GET",
                               f"/api/generation/{job.id}/export/model?format=docx",
                               headers=headers))
        results.append(measure(client, "server DOCX (old path)", "POST",
                               f"/api/generation/{job.id}/export/docx",
                               headers=headers, repeats=1, batch=2))
        results.append(measure(client, "server ZIP (old path)", "POST",
                               f"/api/generation/{job.id}/export/zip",
                               headers=headers, repeats=1, batch=2))

    if SCHEME.exists():
        content = SCHEME.read_bytes()
        results.append(measure(
            client, "upload + DOCX parse",
            "POST", "/api/documents/upload",
            files={"file": (SCHEME.name, content,
                            "application/vnd.openxmlformats-officedocument"
                            ".wordprocessingml.document")},
            headers=headers, repeats=1, batch=2,
        ))

    results.append(measure(
        client, "Paystack webhook (bad signature)", "POST",
        "/api/paystack/webhook",
        json_body={"event": "charge.success", "data": {"reference": "none"}},
        headers={"x-paystack-signature": "bad"},
    ))

    app.dependency_overrides.clear()
    out = ROOT.parent / "docs" / "infrastructure" / "benchmarks"
    out.mkdir(parents=True, exist_ok=True)
    (out / "request-cpu.json").write_text(
        json.dumps({"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                  time.gmtime()),
                    "limit_ms": 10, "results": results}, indent=2),
        encoding="utf-8")

    lines = [
        "| Route | Case | Status | Mean CPU (ms) | p95 batch CPU (ms) | Mean wall (ms) | Requests over 10 ms wall |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for item in results:
        lines.append(
            f"| `{item['route']}` | {item['label']} | {item['status']} | "
            f"{item['median_cpu_ms']} | {item['p95_cpu_ms']} | "
            f"{item['median_wall_ms']} | {item['over_10ms_wall']}/{item['requests_measured']} |")
    (out / "request-cpu.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise

"""Independent backend worker used by the PostgreSQL multi-process tests.

Each invocation is a separate OS process with its own Python interpreter,
SQLAlchemy engine/session factory and FastAPI app instance. It shares only the
PostgreSQL database with its peers, exactly like two uvicorn workers would.

Modes
-----
generate
    POST /api/generation/{scheme}/generate with the supplied config.
resume
    POST /api/generation/{scheme}/generate/resume for a durable job id.
hold-lock
    Acquire the same session advisory lock the generation guard uses, mark the
    supplied job as a live processing job, then sleep until the parent kills
    the process. Proves the lock is released by PostgreSQL on process death.

Synchronisation is file-based (``ready`` + ``go``) so both processes finish
importing and building their app before either sends a request. No production
database or service is contacted.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path


def _wait_for(path: Path, timeout: float = 180.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.05)
    raise SystemExit(f"timed out waiting for {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True,
                        choices=("generate", "resume", "hold-lock"))
    parser.add_argument("--url", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--scheme", required=True)
    parser.add_argument("--config", default="")
    parser.add_argument("--job", default="")
    parser.add_argument("--job-age-minutes", type=int, default=120)
    parser.add_argument("--ready", required=True)
    parser.add_argument("--go", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(backend_dir))
    os.environ["DATABASE_URL"] = args.url

    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(args.url)
    Session = sessionmaker(bind=engine)

    if args.mode == "hold-lock":
        from src.database import GenerationJobDB
        from src.routers.generation import generation_lock_key

        lock_conn = engine.connect()
        lock_conn.execute(
            text("SELECT pg_advisory_lock(:k)"),
            {"k": generation_lock_key(args.user, args.scheme)},
        )
        lock_conn.commit()

        if args.job:
            session = Session()
            try:
                job = session.query(GenerationJobDB).filter(
                    GenerationJobDB.id == args.job).one()
                activity = datetime.utcnow() - timedelta(
                    minutes=args.job_age_minutes)
                job.status = "processing"
                job.created_at = activity
                job.heartbeat_at = activity
                job.completed_at = None
                job.error_message = ""
                session.commit()
            finally:
                session.close()

        Path(args.ready).write_text("ready", encoding="utf-8")
        # The parent terminates this process. PostgreSQL releases the
        # session-level advisory lock when the connection dies.
        while True:
            time.sleep(1)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.auth import get_current_user, require_teacher_workflow
    from src.database import User, get_db
    from src.routers import generation as gen_router

    user_session = Session()
    try:
        user = user_session.query(User).filter(User.id == args.user).one()
        user_session.expunge(user)
    finally:
        user_session.close()

    def _db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app = FastAPI()
    app.include_router(gen_router.router, prefix="/api/generation")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_teacher_workflow] = lambda: user
    app.dependency_overrides[get_db] = _db

    config = {}
    if args.config:
        config = json.loads(Path(args.config).read_text(encoding="utf-8"))

    Path(args.ready).write_text("ready", encoding="utf-8")
    _wait_for(Path(args.go))

    with TestClient(app) as client:
        if args.mode == "generate":
            response = client.post(
                f"/api/generation/{args.scheme}/generate", json=config)
        else:
            response = client.post(
                f"/api/generation/{args.scheme}/generate/resume",
                json={"job_id": args.job},
            )

    try:
        body = response.json()
    except Exception:
        body = {"raw": response.text}

    Path(args.result).write_text(
        json.dumps({"status": response.status_code, "body": body}),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
